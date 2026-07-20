#!/usr/bin/env bash
# Restore Atlas desktop launchers the same way the ISO installer does.
# Run on the VM with sudo after dev-pull:
#   curl -fsSL http://HOST:8765/scripts/dev-refresh-desktop.sh | sudo bash -s -- kaal
#
set -euo pipefail

TARGET_USER="${1:-${SUDO_USER:-}}"
if [[ -z "$TARGET_USER" || "$TARGET_USER" == root ]]; then
  TARGET_USER="$(logname 2>/dev/null || true)"
fi
if [[ -z "$TARGET_USER" || "$TARGET_USER" == root ]]; then
  echo "Usage: sudo $0 <username>" >&2
  exit 1
fi

USER_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
DESK="${XDG_DESKTOP_DIR:-$USER_HOME/Desktop}"
mkdir -p "$DESK"

install_desktop() {
  local name="$1"
  local src="$2"
  local dest="$DESK/${name}.desktop"
  if [[ ! -f "$src" ]]; then
    echo "SKIP missing $src" >&2
    return 0
  fi
  cp -f "$src" "$dest"
  chown "$TARGET_USER:$TARGET_USER" "$dest"
  chmod 755 "$dest"
  echo "OK $dest (755)"
}

# Prefer skel templates (ISO layout); fall back to /usr/share/applications.
install_desktop atlas-launcher \
  "$( [ -f /etc/skel/Desktop/atlas-launcher.desktop ] && echo /etc/skel/Desktop/atlas-launcher.desktop || echo /usr/share/applications/atlas-launcher.desktop )"
install_desktop atlas-command-centre \
  "$( [ -f /etc/skel/Desktop/atlas-command-centre.desktop ] && echo /etc/skel/Desktop/atlas-command-centre.desktop || echo /usr/share/applications/atlas-command-centre.desktop )"

if [[ -x /usr/lib/atlas/trust-desktop-launchers.sh ]]; then
  sudo -u "$TARGET_USER" /usr/lib/atlas/trust-desktop-launchers.sh || true
fi

echo "Done. Log out/in if icons do not appear immediately."
