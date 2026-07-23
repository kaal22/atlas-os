#!/bin/sh
# Apply Atlas wallpaper on KDE Plasma (live + installed sessions).
set -e

pick_wall() {
  base="/usr/share/backgrounds/atlas"
  if [ -n "${ATLAS_WALLPAPER:-}" ] && [ -f "$ATLAS_WALLPAPER" ]; then
    printf '%s' "$ATLAS_WALLPAPER"
    return 0
  fi
  w=1920
  h=1080
  if command -v xrandr >/dev/null 2>&1; then
    geo="$(xrandr --current 2>/dev/null | awk '/\*\+/ {print $1; exit}')"
    if [ -n "$geo" ]; then
      w="${geo%%x*}"
      h="${geo##*x}"
    fi
  fi
  if [ "$w" -ge 3200 ] || [ "$h" -ge 1800 ]; then
    [ -f "$base/atlas-wallpaper-4k.png" ] && { printf '%s' "$base/atlas-wallpaper-4k.png"; return 0; }
  fi
  if [ "$w" -ge 2400 ] || [ "$h" -ge 1350 ]; then
    [ -f "$base/atlas-wallpaper-1440p.png" ] && { printf '%s' "$base/atlas-wallpaper-1440p.png"; return 0; }
  fi
  if [ -f "$base/atlas-wallpaper-1080p.png" ]; then
    printf '%s' "$base/atlas-wallpaper-1080p.png"
    return 0
  fi
  if [ -f "$base/atlas-wallpaper.png" ]; then
    printf '%s' "$base/atlas-wallpaper.png"
    return 0
  fi
  if [ -f "/usr/share/wallpapers/Atlas/contents/images/1920x1080.png" ]; then
    printf '%s' "/usr/share/wallpapers/Atlas/contents/images/1920x1080.png"
    return 0
  fi
  return 1
}

WALL="$(pick_wall)" || exit 0

# Preferred Plasma helper (Plasma 5.25+ / 6)
if command -v plasma-apply-wallpaperimage >/dev/null 2>&1; then
  plasma-apply-wallpaperimage "$WALL" >/dev/null 2>&1 || true
  exit 0
fi

# Fallback: dbus call used by older Plasma
if command -v qdbus >/dev/null 2>&1; then
  qdbus org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "
var allDesktops = desktops();
for (i=0;i<allDesktops.length;i++) {
  d = allDesktops[i];
  d.wallpaperPlugin = 'org.kde.image';
  d.currentConfigGroup = Array('Wallpaper', 'org.kde.image', 'General');
  d.writeConfig('Image', 'file://$WALL');
}" >/dev/null 2>&1 || true
fi

exit 0
