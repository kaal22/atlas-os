#!/usr/bin/env bash
# One-shot dev sync: start HTTP server on host, SSH to VM and pull, stop server.
#
# Usage:
#   ./scripts/dev-push.sh
#   DEV_VM=kaal@192.168.50.50 ./scripts/dev-push.sh
#   ./scripts/dev-push.sh kaal@192.168.50.50
#
# Optional config: scripts/dev-vm.conf
#   DEV_VM=kaal@192.168.50.50
#   DEV_HOST_IP=192.168.50.109   # IP the VM uses to reach this host (auto-detected if unset)
#   DEV_PORT=8765
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

CONF="$ROOT/scripts/dev-vm.conf"
if [[ -f "$CONF" ]]; then
  # shellcheck source=/dev/null
  source "$CONF"
fi

DEV_VM="${DEV_VM:-${1:-}}"
PORT="${DEV_PORT:-${PORT:-8765}}"
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

HOST_IP="${DEV_HOST_IP:-$(pick_ip)}"

usage() {
  cat <<EOF
Usage: $0 [user@vm-host]

Push dev-sync manifest files to the Atlas VM in one command.

  1. Starts a temporary HTTP server on this host (${BIND}:${PORT})
  2. SSHs to the VM and runs dev-pull against ${HOST_IP:-<host-ip>}:${PORT}
  3. Stops the server when done

Set the VM target once in scripts/dev-vm.conf:
  DEV_VM=kaal@192.168.50.50
  DEV_HOST_IP=192.168.50.109

Or pass it inline:
  DEV_VM=kaal@192.168.50.50 $0

Requires passwordless SSH (or interactive SSH) and passwordless sudo on the VM for dev-pull.
EOF
}

if [[ -z "$DEV_VM" ]]; then
  usage >&2
  exit 1
fi

if [[ -z "$HOST_IP" ]]; then
  echo "ERROR: could not detect host IP. Set DEV_HOST_IP in scripts/dev-vm.conf" >&2
  exit 1
fi

echo "=== Atlas dev push ==="
echo "Repo:     $ROOT"
echo "VM:       $DEV_VM"
echo "Host IP:  $HOST_IP (VM will pull from http://${HOST_IP}:${PORT})"
echo "Manifest: $(grep -cve '^#\|^$' scripts/dev-sync.manifest) paths"
echo ""

if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$DEV_VM" true 2>/dev/null; then
  echo "SSH probe failed — continuing anyway (you may be prompted for a password)."
fi

server_pid=""
cleanup() {
  if [[ -n "$server_pid" ]] && kill -0 "$server_pid" 2>/dev/null; then
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
  fi
}
trap cleanup EXIT

python3 -m http.server "$PORT" --bind "$BIND" --directory "$ROOT" >/dev/null 2>&1 &
server_pid=$!

ready=0
for _ in $(seq 1 20); do
  if curl -fsS --connect-timeout 1 "http://127.0.0.1:${PORT}/scripts/dev-sync.manifest" >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.1
done
if [[ "$ready" -ne 1 ]]; then
  echo "ERROR: dev server did not start on port ${PORT}" >&2
  exit 1
fi

echo "Server up — pulling on VM..."
echo ""

pull_cmd="curl -fsSL http://${HOST_IP}:${PORT}/scripts/dev-pull.sh | sudo bash -s -- ${HOST_IP} ${PORT}"
ssh -t "$DEV_VM" "$pull_cmd"

echo ""
echo "Done. Command Centre: http://127.0.0.1:8787/ (on VM)"
