#!/usr/bin/env bash
# Build Calamares branding assets from triangle-glow-master.png as transparent PNGs.
# Uses ImageMagick. Never overwrites master art with 1x1 placeholders.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BRAND="$ROOT/calamares/branding/atlas"
MASTER="$BRAND/triangle-glow-master.png"
PIX="$ROOT/config/includes.chroot/usr/share/pixmaps"
SHARE="$ROOT/config/includes.chroot/usr/share/atlas/branding"
INCL_BRAND="$ROOT/config/includes.chroot/usr/share/atlas/calamares/branding/atlas"

mkdir -p "$BRAND" "$PIX" "$SHARE" "$INCL_BRAND"

if [[ ! -f "$MASTER" ]] || [[ "$(wc -c < "$MASTER")" -lt 1000 ]]; then
  echo "ERROR: missing usable $MASTER" >&2
  exit 1
fi

if ! command -v magick >/dev/null 2>&1; then
  echo "WARNING: ImageMagick (magick) not found — leaving branding files untouched."
  echo "         Install imagemagick. Refusing to write 1x1 placeholders over real art."
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Alpha from luminance; black → transparent; keep white glow
magick "$MASTER" \
  \( +clone -colorspace gray \) \
  -alpha off -compose CopyOpacity -composite \
  -trim +repage \
  -bordercolor none -border 20% \
  -background none -gravity center -extent '%[fx:max(w,h)]x%[fx:max(w,h)]' \
  "$TMP/square.png"

magick "$TMP/square.png" -resize 320x320 -strip PNG32:"$BRAND/logo.png"
magick "$TMP/square.png" -resize 160x160 -strip PNG32:"$BRAND/productIcon.png"
magick -size 640x300 xc:none \( "$TMP/square.png" -resize 200x200 \) \
  -gravity center -compose over -composite -strip PNG32:"$BRAND/welcome.png"
magick -size 920x128 xc:none \( "$TMP/square.png" -resize 90x90 \) \
  -gravity center -compose over -composite -strip PNG32:"$BRAND/banner.png"

# Desktop / menu icon: force RGB to white so Plasma dark themes show a white triangle
# (not a black silhouette). Soften alpha so the glow stays visible at 32–48px.
magick "$TMP/square.png" \
  \( +clone -alpha extract -level 5%,55% \) \
  -alpha off -compose CopyOpacity -composite \
  -channel RGB -evaluate set 100% +channel \
  -resize 256x256 -strip PNG32:"$PIX/atlas.png"
magick "$PIX/atlas.png" -strip PNG32:"$SHARE/logo.png"
mkdir -p "$ROOT/packages/atlas-shell/usr/share/atlas/launcher"
magick "$PIX/atlas.png" -strip PNG32:"$ROOT/packages/atlas-shell/usr/share/atlas/launcher/logo.png"

# hicolor theme sizes for reliable KDE lookup of Icon=atlas
for sz in 16 24 32 48 64 128 256; do
  d="$ROOT/config/includes.chroot/usr/share/icons/hicolor/${sz}x${sz}/apps"
  mkdir -p "$d"
  magick "$PIX/atlas.png" -resize "${sz}x${sz}" -strip PNG32:"$d/atlas.png"
done

cp -a "$BRAND"/. "$INCL_BRAND/"
# Do not ship local preview helpers into the image
rm -f "$INCL_BRAND"/.preview-* "$INCL_BRAND"/.logo-*

echo "Branding regenerated (transparent PNGs) from $MASTER"
wc -c "$BRAND"/logo.png "$BRAND"/productIcon.png "$BRAND"/welcome.png "$BRAND"/banner.png | sed 's|^|  |'
