#!/usr/bin/env bash
# Recover a hung Phase 2 firstboot / payload import on an already-installed VM
# (no reinstall / re-ISO). Typical hang:
#   "Container compose-mysql-1 Waiting" — old compose used
#   depends_on: condition: service_healthy for NOMAD; MySQL never becomes Healthy
#   (often password vs volume mismatch).
#
# On the build host:
#   scp scripts/atlas-recover-payload.sh scripts/repair-nomad-redis.sh \
#       containers/compose/atlas-core.yml user@vm:/tmp/
# In the VM:
#   sudo bash /tmp/atlas-recover-payload.sh
#   # optional: sudo ATLAS_WIPE_MYSQL=1 bash /tmp/atlas-recover-payload.sh
set -euo pipefail

PAYLOAD="${ATLAS_OCI_PAYLOAD:-/usr/share/atlas/payload/atlas-core-oci-payload.tar.zst}"
COMPOSE_SRC="${ATLAS_COMPOSE_SRC:-/usr/share/atlas/compose/atlas-core.yml}"
# Prefer a USB/scp'd fixed compose when present:
for cand in /tmp/atlas-core.yml /tmp/compose/atlas-core.yml "$COMPOSE_SRC"; do
  if [[ -f "$cand" ]]; then
    COMPOSE_SRC="$cand"
    break
  fi
done
COMPOSE_DST="/srv/atlas/compose/atlas-core.yml"
ENV_FILE="/srv/atlas/compose/.env"
LOG_TXT="/srv/atlas/logs/payload-import.log"
LOG_JSON="/srv/atlas/logs/payload-import.json"
WIPE_MYSQL="${ATLAS_WIPE_MYSQL:-0}"
FORCE_RELOAD="${ATLAS_FORCE_RELOAD:-0}"

REQUIRED_IMAGES=(
  "mysql:8.0"
  "redis:7-alpine"
  "qdrant/qdrant:v1.16"
  "ghcr.io/kiwix/kiwix-serve:3.8.2"
  "ghcr.io/crosstalk-solutions/project-nomad:v1.33.0"
)

CORE_SERVICES=(mysql redis qdrant kiwix flatnotes cyberchef kolibri)

echo "=== Atlas Phase 2 hang recovery ==="
if [[ "$(id -u)" -ne 0 ]]; then
  echo "Re-run as root: sudo bash $0" >&2
  exit 1
fi

mkdir -p /etc/atlas/secrets /srv/atlas/{compose,logs,kiwix,maps,users/notes,databases/mysql,models/ollama,nomad-storage,tmp}
chmod 700 /etc/atlas/secrets

# Align secret format with firstboot (hex) so .env stays compose-safe.
[[ -f /etc/atlas/secrets/device-id ]] || openssl rand -hex 16 > /etc/atlas/secrets/device-id
[[ -f /etc/atlas/secrets/mysql-root ]] || openssl rand -hex 24 > /etc/atlas/secrets/mysql-root
[[ -f /etc/atlas/secrets/mysql-nomad ]] || openssl rand -hex 16 > /etc/atlas/secrets/mysql-nomad
[[ -f /etc/atlas/secrets/app-key ]] || openssl rand -hex 32 > /etc/atlas/secrets/app-key
[[ -f /etc/atlas/secrets/redis ]] || openssl rand -hex 16 > /etc/atlas/secrets/redis
chmod 600 /etc/atlas/secrets/*

echo "--- 1) stop hung firstboot / compose waits ---"
systemctl stop atlas-firstboot.service atlas-payload.service 2>/dev/null || true
# Kill any stuck docker compose that is waiting on mysql healthy
pkill -f 'docker[- ]compose.*atlas-core' 2>/dev/null || true
pkill -f 'compose.*Waiting' 2>/dev/null || true
sleep 1

systemctl start docker.service || true
for _ in $(seq 1 90); do
  docker info >/dev/null 2>&1 && break
  sleep 1
done
docker info >/dev/null 2>&1 || { echo "Docker daemon not ready" >&2; exit 1; }

echo "--- 2) install fixed compose (source: $COMPOSE_SRC) ---"
[[ -f "$COMPOSE_SRC" ]] || { echo "missing compose at $COMPOSE_SRC" >&2; exit 1; }
cp -f "$COMPOSE_SRC" "$COMPOSE_DST"
if grep -q 'condition: service_healthy' "$COMPOSE_DST"; then
  echo "WARN: compose still has service_healthy depends_on — NOMAD may block" >&2
fi

umask 077
cat > "$ENV_FILE" <<EOF
ATLAS_MYSQL_ROOT_PASSWORD=$(cat /etc/atlas/secrets/mysql-root)
ATLAS_MYSQL_PASSWORD=$(cat /etc/atlas/secrets/mysql-nomad)
ATLAS_APP_KEY=$(cat /etc/atlas/secrets/app-key)
EOF
chmod 600 "$ENV_FILE"

compose() {
  if docker compose version >/dev/null 2>&1; then
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_DST" "$@"
  else
    docker-compose --env-file "$ENV_FILE" -f "$COMPOSE_DST" "$@"
  fi
}

echo "--- 3) optional MySQL volume wipe (secret mismatch recovery) ---"
if [[ "$WIPE_MYSQL" == "1" ]]; then
  echo "ATLAS_WIPE_MYSQL=1 — stopping mysql and wiping /srv/atlas/databases/mysql"
  compose stop mysql 2>/dev/null || true
  compose rm -f mysql 2>/dev/null || true
  rm -rf /srv/atlas/databases/mysql
  mkdir -p /srv/atlas/databases/mysql
else
  # Auto-hint: if mysql is up but unhealthy, print guidance (do not wipe unless asked).
  if compose ps mysql 2>/dev/null | grep -qi unhealthy; then
    echo "NOTE: mysql looks unhealthy. If healthcheck auth fails (secrets ≠ volume),"
    echo "      re-run with:  sudo ATLAS_WIPE_MYSQL=1 bash $0"
  fi
fi

if [[ ! -f /srv/atlas/kiwix/library.xml ]]; then
  cat > /srv/atlas/kiwix/library.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<library version="20110515">
</library>
EOF
fi
chmod -R a+rX /srv/atlas/kiwix 2>/dev/null || true

images_ok=1
for need in "${REQUIRED_IMAGES[@]}"; do
  if ! docker image inspect "$need" >/dev/null 2>&1; then
    images_ok=0
    echo "missing image: $need"
  fi
done

echo "--- 4) payload images ---"
if [[ "$FORCE_RELOAD" == "1" || "$images_ok" -eq 0 ]]; then
  [[ -f "$PAYLOAD" ]] || { echo "MISSING $PAYLOAD" >&2; exit 1; }
  echo "Loading payload (FORCE_RELOAD=$FORCE_RELOAD images_ok=$images_ok)..."
  TMP="/srv/atlas/tmp/payload-recover.$$"
  rm -rf "$TMP"
  mkdir -p "$TMP"
  trap 'rm -rf "$TMP"' EXIT
  zstd -d -c "$PAYLOAD" | tar -x -C "$TMP"
  shopt -s nullglob
  tars=("$TMP"/oci/*.tar)
  shopt -u nullglob
  [[ ${#tars[@]} -gt 0 ]] || { echo "No OCI tars in payload" >&2; exit 1; }
  {
    echo "=== recover $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    for tar in "${tars[@]}"; do
      base="$(basename "$tar")"
      echo "Loading $base"
      docker load -i "$tar"
    done
  } | tee -a "$LOG_TXT"
else
  echo "REQUIRED_IMAGES already present — skipping extract/load (ATLAS_FORCE_RELOAD=1 to force)"
fi

echo "--- 5) bring up core (no healthy wait on NOMAD) ---"
{
  echo "=== compose up $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  compose up -d "${CORE_SERVICES[@]}"
  echo "core up ok"
  compose up -d atlas-nomad-core || echo "WARN: nomad up failed (best-effort)"
  compose ps || true
} | tee -a "$LOG_TXT"

echo "--- 6) mark firstboot complete ---"
rm -f /etc/atlas/firstboot-pending
date -u +%Y-%m-%dT%H:%M:%SZ > /etc/atlas/firstboot-done
python3 - "$LOG_JSON" <<'PY'
import json, sys, datetime
from pathlib import Path
path = sys.argv[1]
msg = {
  "ok": True,
  "message": "recovered_via_atlas-recover-payload",
  "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
Path(path).write_text(json.dumps(msg, indent=2) + "\n")
Path("/srv/atlas/logs/firstboot.json").write_text(json.dumps({
  "ok": True,
  "message": "recovered_via_atlas-recover-payload",
  "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}, indent=2) + "\n")
PY

if command -v ollama >/dev/null; then
  systemctl enable --now ollama.service 2>/dev/null || systemctl start ollama.service || true
fi

echo
echo "=== listeners ==="
ss -lntp 2>/dev/null | grep 127.0.0.1 || true
echo "=== quick health ==="
for u in \
  http://127.0.0.1:8080/ \
  http://127.0.0.1:6333/readyz \
  http://127.0.0.1:8090/api/health \
  http://127.0.0.1:11434/api/tags
do
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 2 "$u" 2>/dev/null || echo 000)
  echo "$code  $u"
done
if command -v atlas-health >/dev/null; then
  atlas-health || true
fi

echo
echo "Done. If NOMAD still down and mysql was unhealthy, wipe DB and retry:"
echo "  sudo ATLAS_WIPE_MYSQL=1 bash $0"
echo "Or only repair redis/nomad:"
echo "  sudo bash /tmp/repair-nomad-redis.sh"
