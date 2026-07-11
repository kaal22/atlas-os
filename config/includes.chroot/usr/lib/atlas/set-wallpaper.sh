#!/bin/sh
# Apply Atlas wallpaper on KDE Plasma (live + installed sessions).
set -e
WALL="${ATLAS_WALLPAPER:-/usr/share/backgrounds/atlas/atlas-wallpaper.png}"

if [ ! -f "$WALL" ]; then
  WALL="/usr/share/backgrounds/atlas/atlas-wallpaper-1080p.png"
fi
if [ ! -f "$WALL" ]; then
  WALL="/usr/share/wallpapers/Atlas/contents/images/1920x1080.png"
fi
if [ ! -f "$WALL" ]; then
  exit 0
fi

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
