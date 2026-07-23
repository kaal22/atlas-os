#!/usr/bin/env bash
# Pull Atlas dev files from the host dev-serve.sh instance into this VM/install.
#
# Usage (after starting ./scripts/dev-serve.sh on the host):
#   curl -fsSL http://HOST:8765/scripts/dev-pull.sh | sudo bash -s -- HOST [PORT]
# Or from a checkout on the VM:
#   sudo ./scripts/dev-pull.sh HOST [PORT]
#
# Installs packages/… paths from scripts/dev-sync.manifest into /usr (and a few
# /srv compose copies). Command Centre serves Maps from /usr/share/atlas/maps-viewer
# (not a .deb snapshot). UI HTML is loaded once at process start — restart required.
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

# Mode for install(1): keep scripts/binaries executable (644 broke sync-nomad-maps.sh).
install_mode() {
  local dest="$1" file="$2"
  case "$dest" in
    /usr/bin/*|/bin/*|/sbin/*|/usr/sbin/*) echo 755; return ;;
  esac
  case "$dest" in
    *.sh) echo 755; return ;;
  esac
  if head -c 64 "$file" 2>/dev/null | head -n 1 | grep -q '^#!'; then
    echo 755
    return
  fi
  echo 644
}

pulled=0
need_maps_republish=0
declare -A restart_units=()

while IFS='|' read -r src dest svc || [[ -n "${src:-}" ]]; do
  [[ -z "${src:-}" || "$src" =~ ^[[:space:]]*# ]] && continue
  src="${src#"${src%%[![:space:]]*}"}"
  src="${src%"${src##*[![:space:]]}"}"
  dest="${dest#"${dest%%[![:space:]]*}"}"
  dest="${dest%"${dest##*[![:space:]]}"}"
  svc="${svc#"${svc%%[![:space:]]*}"}"
  svc="${svc%"${svc##*[![:space:]]}"}"

  url="${BASE}/${src}"
  tmp="$tmpdir/$(basename "$src").$$.$pulled"
  echo "→ ${src}"
  curl -fsS --connect-timeout 10 --max-time 120 "$url" -o "$tmp"
  mode="$(install_mode "$dest" "$tmp")"
  install -D -m "$mode" "$tmp" "$dest"
  pulled=$((pulled + 1))

  if [[ -n "$svc" ]]; then
    restart_units["$svc"]=1
  fi

  # Maps viewer lives under /usr/share; also republish NOMAD's /srv copy after pull.
  case "$dest" in
    /usr/share/atlas/maps-viewer/*|/usr/share/atlas/nomad-map-assets/*|/usr/lib/atlas/sync-nomad-maps.sh)
      need_maps_republish=1
      # CC reads viewer files from disk each request; restart still refreshes in-memory UI
      # and any command_centre.py maps-route changes pulled in the same run.
      restart_units["atlas-command-centre.service"]=1
      ;;
  esac
done < "$tmpdir/manifest"

echo ""
echo "Pulled ${pulled} file(s)."

if ((need_maps_republish)); then
  # Secondary path: NOMAD (:8090) reads /srv/.../viewer/. Command Centre (:8787)
  # serves Maps directly from /usr/share/atlas/maps-viewer — already updated above.
  echo "Republishing Maps viewer → /srv/atlas/nomad-storage/maps/viewer/ (NOMAD only; CC uses /usr/share)"
  if [[ -f /usr/lib/atlas/sync-nomad-maps.sh ]]; then
    if ATLAS_ROOT=/srv/atlas bash /usr/lib/atlas/sync-nomad-maps.sh; then
      echo "   sync-nomad-maps.sh OK"
    else
      echo "   WARN: sync-nomad-maps.sh failed (non-fatal; CC /maps/ still uses /usr/share)" >&2
    fi
  else
    echo "   WARN: /usr/lib/atlas/sync-nomad-maps.sh missing (OK for CC :8787 /maps/)" >&2
  fi
elif ((pulled > 0)); then
  echo "(No Maps viewer files in this pull — skip NOMAD republish; CC /maps/ unchanged.)"
fi

restarted=()
if ((${#restart_units[@]})); then
  for svc in "${!restart_units[@]}"; do
    if systemctl list-unit-files "$svc" >/dev/null 2>&1 || systemctl cat "$svc" >/dev/null 2>&1; then
      if systemctl restart "$svc" 2>/dev/null; then
        restarted+=("$svc")
        echo "Restarted ${svc}"
      else
        echo "WARN: could not restart ${svc}" >&2
      fi
    fi
  done
fi

if ((${#restarted[@]})); then
  echo "Units restarted: ${restarted[*]}"
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
echo "Maps viewer:    http://127.0.0.1:8787/maps/?country=uk"
echo ""
echo "Verify Maps pull landed (on the VM):"
echo "  ls -l --time-style=long-iso /usr/share/atlas/maps-viewer/lib/atlas-maps-app.js"
echo "  curl -sI http://127.0.0.1:8787/maps/lib/atlas-maps-app.js | grep -i cache"
echo "  hard-refresh the browser (Ctrl+Shift+R) after pull"
echo ""
if [[ -n "$REFRESH_USER" && "$REFRESH_USER" != root ]]; then
  echo "Desktop refreshed for ${REFRESH_USER}."
else
  echo "If Service Check vanished from the desktop, run on the VM:"
  echo "  curl -fsSL ${BASE}/scripts/dev-refresh-desktop.sh | sudo bash -s -- kaal"
fi
