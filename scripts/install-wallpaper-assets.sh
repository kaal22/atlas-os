#!/usr/bin/env bash
# Regenerate Atlas desktop wallpaper assets from assets/atlas-wallpaper-master.png
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${1:-$ROOT/assets/atlas-wallpaper-master.png}"
WALL="$ROOT/config/includes.chroot/usr/share/backgrounds/atlas"
PLASMA="$ROOT/config/includes.chroot/usr/share/wallpapers/Atlas/contents/images"

if [ ! -f "$SRC" ]; then
  echo "ERROR: wallpaper source not found: $SRC" >&2
  exit 1
fi

mkdir -p "$WALL" "$PLASMA"

magick "$SRC" -strip "$WALL/atlas-wallpaper.png"
cp "$WALL/atlas-wallpaper.png" "$WALL/atlas-default.png"

for spec in "1080p:1920x1080" "1440p:2560x1440" "4k:3840x2160"; do
  label="${spec%%:*}"
  dim="${spec##*:}"
  magick "$SRC" -strip -resize "${dim}!" "$WALL/atlas-wallpaper-${label}.png"
done

magick "$SRC" -strip -resize 1920x1080! "$PLASMA/1920x1080.png"
magick "$SRC" -strip -resize 2560x1440! "$PLASMA/2560x1440.png"
magick "$SRC" -strip -resize 3840x2160! "$PLASMA/3840x2160.png"
cp "$WALL/atlas-wallpaper.png" "$PLASMA/1024x576.png"

echo "Wallpaper assets installed from $SRC"
identify "$WALL/atlas-wallpaper.png" "$WALL/atlas-wallpaper-1080p.png" "$WALL/atlas-wallpaper-4k.png"
