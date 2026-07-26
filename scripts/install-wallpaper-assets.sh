#!/usr/bin/env bash
# Regenerate Arcalium desktop wallpaper assets from assets/arcaliumos.png
# (native 2560×1440). Optional override: scripts/install-wallpaper-assets.sh /path/to.png
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:-$ROOT/assets/arcaliumos.png}"
WALL="$ROOT/config/includes.chroot/usr/share/backgrounds/atlas"
PLASMA="$ROOT/config/includes.chroot/usr/share/wallpapers/Atlas/contents/images"

if [ ! -f "$SRC" ]; then
  echo "ERROR: wallpaper source not found: $SRC" >&2
  exit 1
fi

mkdir -p "$WALL" "$PLASMA"

# Native / default install path used by SDDM + set-wallpaper fallbacks.
magick "$SRC" -strip "$WALL/arcalium-default.png"

# Drop superseded Atlas-named assets if present from older trees.
rm -f \
  "$WALL/atlas-default.png" \
  "$WALL/atlas-wallpaper.png" \
  "$WALL"/atlas-wallpaper-*.png

for spec in "1080p:1920x1080" "1440p:2560x1440" "4k:3840x2160"; do
  label="${spec%%:*}"
  dim="${spec##*:}"
  magick "$SRC" -strip -resize "${dim}!" "$WALL/arcalium-wallpaper-${label}.png"
done

magick "$SRC" -strip -resize 1024x576! "$PLASMA/1024x576.png"
magick "$SRC" -strip -resize 1920x1080! "$PLASMA/1920x1080.png"
magick "$SRC" -strip -resize 2560x1440! "$PLASMA/2560x1440.png"
magick "$SRC" -strip -resize 3840x2160! "$PLASMA/3840x2160.png"

echo "Wallpaper assets installed from $SRC"
identify \
  "$WALL/arcalium-default.png" \
  "$WALL/arcalium-wallpaper-1080p.png" \
  "$WALL/arcalium-wallpaper-1440p.png" \
  "$WALL/arcalium-wallpaper-4k.png"
