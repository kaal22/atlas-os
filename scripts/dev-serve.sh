#!/usr/bin/env bash
# Serve the Atlas repo over HTTP so a VM can pull dev changes (no scp).
#
# On the Debian build host (repo root):
#   ./scripts/dev-serve.sh
#
# On the Atlas VM (QEMU user networking — host is usually 10.0.2.2):
#   curl -fsSL http://10.0.2.2:8765/scripts/dev-pull.sh | sudo bash -s -- 10.0.2.2
#
# VMware / bridged LAN — use the host IP printed below:
#   curl -fsSL http://192.168.x.x:8765/scripts/dev-pull.sh | sudo bash -s -- 192.168.x.x
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8765}"
BIND="${BIND:-0.0.0.0}"

pick_ip() {
  local ip=""
  if command -v ip >/dev/null 2>&1; then
    ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}')"
  fi
  if [[ -z "$ip" ]] && command -v hostname >/dev/null 2>&1; then
    ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  fi
  printf '%s' "$ip"
}

HOST_IP="$(pick_ip)"
LAN_IPS=""
if command -v ip >/dev/null 2>&1; then
  LAN_IPS="$(ip -4 -o addr show scope global 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | tr '\n' ' ')"
fi

echo "=== Atlas dev sync server ==="
echo "Repo:  $ROOT"
echo "Listen: ${BIND}:${PORT}"
echo ""
echo "VM pull (copy one line — adjust IP for your network):"
echo ""
if [[ -n "$HOST_IP" ]]; then
  echo "  curl -fsSL http://${HOST_IP}:${PORT}/scripts/dev-pull.sh | sudo bash -s -- ${HOST_IP} ${PORT}"
fi
echo "  curl -fsSL http://10.0.2.2:${PORT}/scripts/dev-pull.sh | sudo bash -s -- 10.0.2.2 ${PORT}   # QEMU user net"
echo ""
if [[ -n "$LAN_IPS" ]]; then
  echo "Host addresses: ${LAN_IPS}"
fi
echo ""
echo "Manifest: scripts/dev-sync.manifest ($(grep -cve '^#\|^$' scripts/dev-sync.manifest) paths)"
echo "Press Ctrl+C to stop."
echo ""

exec python3 -m http.server "$PORT" --bind "$BIND" --directory "$ROOT"
