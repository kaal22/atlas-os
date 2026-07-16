#!/usr/bin/env bash
# Collect Phase 3 identity/security evidence on an installed Atlas OS system (or VM).
# Usage: sudo ./scripts/collect-phase3-evidence.sh [outdir]
set -euo pipefail

OUT="${1:-tests/installer/evidence/phase3-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT"

CC_DIRECT="${ATLAS_CC_DIRECT:-http://127.0.0.1:8787}"
CC_PROXY="${ATLAS_CC_PROXY:-http://127.0.0.1}"
SOCK="${ATLAS_SYSTEM_SOCK:-/run/atlas/system.sock}"

{
  echo "=== date ==="
  date -u
  echo "=== network mode ==="
  cat /etc/atlas/network-mode 2>/dev/null || echo "(missing — expected private_device after firstboot)"
  echo "=== ufw status ==="
  ufw status verbose 2>/dev/null || echo "(ufw unavailable)"
} | tee "$OUT/firewall.txt"

{
  echo "=== units ==="
  for u in atlas-system-daemon atlas-command-centre atlas-proxy nginx; do
    echo "-- $u --"
    systemctl is-enabled "$u.service" 2>/dev/null || echo "not-enabled"
    systemctl is-active "$u.service" 2>/dev/null || echo "inactive"
  done
} | tee "$OUT/units.txt"

{
  echo "=== listen (ss) ==="
  ss -lntp 2>/dev/null || netstat -lntp 2>/dev/null || true
  echo
  echo "=== expect 127.0.0.1:80 (nginx) and 127.0.0.1:8787 (CC); no *:8787 ==="
  ss -lntp 2>/dev/null | grep -E ':80|:8787' || true
} | tee "$OUT/listen.txt"

probe() {
  local url="$1"
  local code
  code=$(curl -sS -o /tmp/atlas-p3-body -w '%{http_code}' --max-time 3 "$url" || echo 000)
  echo "$code  $url"
  if [[ -f /tmp/atlas-p3-body ]]; then
    head -c 200 /tmp/atlas-p3-body | tr '\n' ' '
    echo
  fi
}

{
  echo "=== unauthenticated API (expect 401) ==="
  probe "$CC_DIRECT/api/system/health"
  probe "$CC_PROXY/api/system/health"
  echo "=== bootstrap status (expect 200) ==="
  probe "$CC_DIRECT/api/auth/bootstrap"
  probe "$CC_PROXY/api/auth/bootstrap"
} | tee "$OUT/http.txt"

{
  echo "=== daemon socket ==="
  if [[ -S "$SOCK" ]]; then
    echo "socket exists: $SOCK"
    python3 - <<PY || true
import json, os, socket, time
sock_path = os.environ.get("ATLAS_SYSTEM_SOCK", "$SOCK")
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.settimeout(2)
s.connect(sock_path)
tok = f"cap:system.health.read:p3:{int(time.time())+60}"
s.sendall((json.dumps({"method":"system.health.read","token":tok})+"\n").encode())
print(s.recv(4096).decode())
s.close()
PY
  else
    echo "socket missing: $SOCK"
  fi
} | tee "$OUT/daemon.txt"

{
  echo "=== audit log samples ==="
  for f in /srv/atlas/logs/atlas-audit.jsonl /srv/atlas/logs/system-daemon-audit.jsonl; do
    echo "-- $f --"
    if [[ -f "$f" ]]; then
      tail -n 20 "$f" || true
    else
      echo "(absent)"
    fi
  done
} | tee "$OUT/audit.txt"

# Lightweight local integration-ish checks when CC is up
{
  echo "=== auth flow (bootstrap/login) ==="
  TMP=$(mktemp -d)
  COOKIE="$TMP/cookies.txt"
  boot=$(curl -sS --max-time 3 "$CC_DIRECT/api/auth/bootstrap" || echo '{}')
  echo "bootstrap: $boot"
  if echo "$boot" | grep -q '"needs_bootstrap": true'; then
    curl -sS -c "$COOKIE" -b "$COOKIE" -H 'Content-Type: application/json' \
      -d '{"username":"evidence-owner","password":"EvidencePass-1"}' \
      "$CC_DIRECT/api/auth/bootstrap" | tee "$OUT/bootstrap-resp.json" || true
  else
    echo "(already bootstrapped — skip create)"
  fi
  code=$(curl -sS -o /tmp/atlas-p3-auth -w '%{http_code}' -b "$COOKIE" --max-time 3 \
    "$CC_DIRECT/api/system/health" || echo 000)
  echo "authed health: $code"
  cat /tmp/atlas-p3-auth 2>/dev/null | head -c 300 || true
  echo
} | tee "$OUT/auth-flow.txt"

echo "Phase 3 evidence written to $OUT"
