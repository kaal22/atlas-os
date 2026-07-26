#!/usr/bin/env bash
# Regenerate Arcalium Plymouth theme assets from assets/plymouthsplash.png
# (master ~5504×3072). Optional override: scripts/install-plymouth-assets.sh /path/to.png
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:-$ROOT/assets/plymouthsplash.png}"
THEME="$ROOT/config/includes.chroot/usr/share/plymouth/themes/arcalium"

if [ ! -f "$SRC" ]; then
  echo "ERROR: plymouth splash source not found: $SRC" >&2
  exit 1
fi

mkdir -p "$THEME"

# Ship a 1080p cover-ready JPEG splash (~250KB) so initramfs stays lean;
# arcalium.script cover-scales at runtime.
magick "$SRC" -strip -resize 1920x1080^ -gravity center -extent 1920x1080 \
  -quality 88 "$THEME/background.jpg"
rm -f "$THEME/background.png"

# Minimal password UI (dark translucent field + light dots) for LUKS/crypt prompts.
magick -size 320x48 xc:'rgba(20,20,28,180)' \
  -fill 'rgba(255,255,255,40)' -draw 'roundrectangle 1,1 318,46 8,8' \
  "$THEME/password_field.png"
magick -size 160x24 xc:'rgba(20,20,28,180)' \
  -fill 'rgba(255,255,255,40)' -draw 'roundrectangle 1,1 158,22 6,6' \
  "$THEME/password_field16.png"
magick -size 12x12 xc:none -fill 'rgba(240,240,245,220)' -draw 'circle 6,6 6,1' \
  "$THEME/password_dot.png"
magick -size 8x8 xc:none -fill 'rgba(240,240,245,220)' -draw 'circle 4,4 4,1' \
  "$THEME/password_dot16.png"

echo "Plymouth assets installed from $SRC → $THEME"
identify "$THEME/background.jpg"
