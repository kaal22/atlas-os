#!/bin/sh
# Apply Atlas wallpaper to every XFCE monitor (live + installed sessions).
set -e
WALL="${ATLAS_WALLPAPER:-/usr/share/backgrounds/atlas/atlas-wallpaper.png}"

if [ ! -f "$WALL" ]; then
  WALL="/usr/share/backgrounds/atlas/atlas-wallpaper-1080p.png"
fi
if [ ! -f "$WALL" ]; then
  exit 0
fi

if ! command -v xfconf-query >/dev/null 2>&1; then
  exit 0
fi

# Create/update any existing last-image properties
props="$(xfconf-query -c xfce4-desktop -l 2>/dev/null | grep -E '/last-image$' || true)"
if [ -n "$props" ]; then
  echo "$props" | while read -r prop; do
    [ -n "$prop" ] || continue
    base="${prop%/last-image}"
    xfconf-query -c xfce4-desktop -p "$prop" -s "$WALL" || true
    xfconf-query -c xfce4-desktop -p "$base/image-style" -s 5 2>/dev/null || \
      xfconf-query -c xfce4-desktop -p "$base/image-style" -n -t int -s 5 2>/dev/null || true
  done
else
  # Fresh profile: seed monitor0
  xfconf-query -c xfce4-desktop -p /backdrop/screen0/monitor0/last-image -n -t string -s "$WALL" 2>/dev/null || \
    xfconf-query -c xfce4-desktop -p /backdrop/screen0/monitor0/last-image -s "$WALL" 2>/dev/null || true
  xfconf-query -c xfce4-desktop -p /backdrop/screen0/monitor0/image-style -n -t int -s 5 2>/dev/null || \
    xfconf-query -c xfce4-desktop -p /backdrop/screen0/monitor0/image-style -s 5 2>/dev/null || true
fi

exit 0
