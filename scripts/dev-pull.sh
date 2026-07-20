#!/usr/bin/env bash
# Pull Atlas dev files from the host dev-serve.sh instance into this VM/install.
#
# Usage (after starting ./scripts/dev-serve.sh on the host):
#   curl -fsSL http://HOST:8765/scripts/dev-pull.sh | sudo bash -s -- HOST [PORT]
# Or from a checkout on the VM:
#   sudo ./scripts/dev-pull.sh HOST [PORT]
#
set -euo pipefail

HOST="${1:-10.0.2.2}"
PORT="${2:-8765}"
BASE="http://${HOST}:${PORT}"
MANIFEST_URL="${BASE}/scripts/dev-sync.manifest"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Re-run with sudo (installs into /usr)." >&2
  exit 1
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

echo "=== Atlas dev pull ==="
echo "Host: ${BASE}"
echo ""

if ! curl -fsS --connect-timeout 5 --max-time 30 "$MANIFEST_URL" -o "$tmpdir/manifest"; then
  echo "ERROR: cannot fetch manifest from ${MANIFEST_URL}" >&2
  echo "Start the host server: ./scripts/dev-serve.sh" >&2
  echo "QEMU user networking: host is usually 10.0.2.2" >&2
  exit 1
fi

pulled=0
restarted=()

while IFS='|' read -r src dest svc || [[ -n "${src:-}" ]]; do
  [[ -z "${src:-}" || "$src" =~ ^[[:space:]]*# ]] && continue
  src="${src#"${src%%[![:space:]]*}"}"
  src="${src%"${src##*[![:space:]]}"}"
  dest="${dest#"${dest%%[![:space:]]*}"}"
  dest="${dest%"${dest##*[![:space:]]}"}"
  svc="${svc#"${svc%%[![:space:]]*}"}"
  svc="${svc%"${svc##*[![:space:]]}"}"

  url="${BASE}/${src}"
  tmp="$tmpdir/$(basename "$src")"
  echo "→ ${src}"
  curl -fsS --connect-timeout 10 --max-time 120 "$url" -o "$tmp"
  install -D -m 644 "$tmp" "$dest"
  pulled=$((pulled + 1))

  if [[ -n "$svc" ]]; then
    if systemctl is-enabled "$svc" >/dev/null 2>&1 || systemctl list-unit-files "$svc" >/dev/null 2>&1; then
      if systemctl restart "$svc" 2>/dev/null; then
        restarted+=("$svc")
        echo "   restarted ${svc}"
      fi
    fi
  fi
done < "$tmpdir/manifest"

echo ""
echo "Pulled ${pulled} file(s)."
if ((${#restarted[@]})); then
  echo "Restarted: ${restarted[*]}"
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi

REFRESH_USER="${SUDO_USER:-}"
if [[ -n "$REFRESH_USER" && "$REFRESH_USER" != root ]]; then
  if curl -fsS --connect-timeout 5 "${BASE}/scripts/dev-refresh-desktop.sh" -o "$tmpdir/dev-refresh-desktop.sh" 2>/dev/null; then
    bash "$tmpdir/dev-refresh-desktop.sh" "$REFRESH_USER" || true
  fi
fi

echo "Command Centre: http://127.0.0.1:8787/"
echo ""
if [[ -n "$REFRESH_USER" && "$REFRESH_USER" != root ]]; then
  echo "Desktop refreshed for ${REFRESH_USER}."
else
  echo "If Service Check vanished from the desktop, run on the VM:"
  echo "  curl -fsSL ${BASE}/scripts/dev-refresh-desktop.sh | sudo bash -s -- kaal"
fi
