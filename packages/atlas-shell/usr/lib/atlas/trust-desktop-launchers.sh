#!/bin/sh
# Plasma opens non-executable Desktop *.desktop files in Kate instead of launching them.
set -e
desk="${XDG_DESKTOP_DIR:-$HOME/Desktop}"
[ -d "$desk" ] || desk="$HOME/Desktop"
[ -d "$desk" ] || exit 0
for f in "$desk"/atlas-launcher.desktop "$desk"/atlas-command-centre.desktop; do
  [ -f "$f" ] || continue
  chmod a+x "$f" 2>/dev/null || true
done
