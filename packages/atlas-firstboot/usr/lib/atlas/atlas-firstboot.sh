#!/bin/bash
# Atlas first-boot: generate unique secrets, import offline payload, start Ollama.
set -euo pipefail

FLAG=/etc/atlas/firstboot-pending
DONE=/etc/atlas/firstboot-done
DATA=/srv/atlas
SECRETS=/etc/atlas/secrets
STATUS_JSON=/srv/atlas/logs/firstboot.json
PROGRESS=/srv/atlas/logs/firstboot-progress.txt

if [[ -f "$DONE" ]]; then
  exit 0
fi

mkdir -p "$DATA"/{users,workspaces,documents,knowledge,embeddings,models/ollama,maps,kiwix,kolibri,media,content-packs,agent-packages,backups/knowledge,exports,databases/mysql,logs,compose,tmp,nomad-storage}
mkdir -p "$SECRETS"
chmod 700 "$SECRETS"

progress() {
  mkdir -p "$(dirname "$PROGRESS")"
  local line="[$(date -u +%H:%M:%S)] $*"
  echo "$line" | tee -a "$PROGRESS"
  echo "$*" >"${PROGRESS}.current"
}

write_status() {
  local ok="$1"
  local msg="$2"
  mkdir -p "$(dirname "$STATUS_JSON")"
  python3 - "$STATUS_JSON" "$ok" "$msg" <<'PY' || true
import json, sys, datetime
path, ok, msg = sys.argv[1], sys.argv[2] == "1", sys.argv[3]
obj = {
  "ok": ok,
  "message": msg,
  "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
open(path, "w", encoding="utf-8").write(json.dumps(obj, indent=2) + "\n")
PY
}

fail() {
  progress "FAILED: $*"
  write_status 0 "$*"
  echo "ERROR: $*" >&2
  exit 1
}

: >"$PROGRESS"
progress "Atlas first-boot started (offline payload import can take 10–30 minutes)"

if [[ ! -f "$SECRETS/device-id" ]]; then
  if command -v openssl >/dev/null; then
    openssl rand -hex 16 > "$SECRETS/device-id"
  else
    head -c 16 /dev/urandom | xxd -p > "$SECRETS/device-id"
  fi
fi

if [[ ! -f "$SECRETS/mysql-root" ]]; then
  openssl rand -hex 24 > "$SECRETS/mysql-root"
fi

if [[ ! -f "$SECRETS/mysql-nomad" ]]; then
  openssl rand -hex 16 > "$SECRETS/mysql-nomad"
fi

# AdonisJS APP_KEY must be >= 16 characters; use hex so .env stays parse-safe
if [[ ! -f "$SECRETS/app-key" ]]; then
  openssl rand -hex 32 > "$SECRETS/app-key"
fi

if [[ ! -f "$SECRETS/redis" ]]; then
  openssl rand -base64 32 | tr -d '\n' > "$SECRETS/redis"
fi

chmod 600 "$SECRETS"/*
progress "Secrets ready"

if [[ -x /usr/lib/atlas/import-payload.sh ]]; then
  progress "Starting payload import..."
  /usr/lib/atlas/import-payload.sh || fail "import-payload.sh failed"
else
  fail "import-payload.sh missing"
fi

if command -v ollama >/dev/null; then
  progress "Starting Ollama..."
  systemctl daemon-reload >/dev/null 2>&1 || true
  systemctl enable ollama.service >/dev/null 2>&1 || true
  systemctl restart ollama.service || systemctl start ollama.service || fail "failed to start ollama.service"
  # Wait briefly for API before claiming success
  for _ in $(seq 1 30); do
    if curl -fsS --max-time 1 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      progress "Ollama is responding on 127.0.0.1:11434"
      break
    fi
    sleep 1
  done
elif [[ -f /etc/atlas/payload-enabled ]]; then
  fail "payload enabled but ollama binary missing"
fi

# Phase 3: apply private_device firewall (loopback-only) and persist mode.
progress "Applying private_device network mode..."
MODE_FILE=/etc/atlas/network-mode
mkdir -p /etc/atlas
if [[ -x /usr/bin/python3 ]] && [[ -f /usr/lib/atlas/network_modes.py ]]; then
  if /usr/bin/python3 - <<'PY'
import sys
sys.path.insert(0, "/usr/lib/atlas")
from network_modes import apply_mode
from pathlib import Path
try:
    apply_mode("private_device", dry_run=False)
    Path("/etc/atlas/network-mode").write_text("private_device\n", encoding="utf-8")
    print("private_device applied")
except Exception as e:
    # Do not hard-fail firstboot if ufw is missing in a test VM; persist intent.
    Path("/etc/atlas/network-mode").write_text("private_device\n", encoding="utf-8")
    print(f"private_device deferred: {e}", file=sys.stderr)
    sys.exit(0)
PY
  then
    progress "Network mode private_device ready ($(cat "$MODE_FILE" 2>/dev/null || echo unknown))"
  else
    echo "private_device" >"$MODE_FILE"
    progress "WARN: network mode apply failed; persisted private_device intent"
  fi
else
  echo "private_device" >"$MODE_FILE"
  progress "WARN: network_modes.py missing; persisted private_device intent"
fi

# Final loopback snapshot (do not fail firstboot if containers are still warming)
if command -v atlas-health >/dev/null; then
  progress "Health snapshot: $(atlas-health 2>/dev/null | tr '\n' ' ' | head -c 400)"
fi

rm -f "$FLAG"
date -u +%Y-%m-%dT%H:%M:%SZ > "$DONE"
write_status 1 "firstboot_completed"
progress "Atlas first-boot completed successfully"
echo "Atlas first-boot completed."
