#!/bin/sh
# Apply Atlas wallpaper on KDE Plasma (live + installed sessions).
set -e

LOG="${ATLAS_WALLPAPER_LOG:-/tmp/atlas-wallpaper.log}"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$LOG" 2>/dev/null || true
}

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

# Wait briefly for plasmashell on session start (autostart can race the shell).
wait_for_plasma() {
  i=0
  while [ "$i" -lt 15 ]; do
    if pgrep -x plasmashell >/dev/null 2>&1; then
      return 0
    fi
    i=$((i + 1))
    sleep 1
  done
  return 1
}

apply_via_helper() {
  wall="$1"
  if ! command -v plasma-apply-wallpaperimage >/dev/null 2>&1; then
    return 1
  fi
  # Retry a few times — helper can fail before Plasma finishes loading.
  n=0
  while [ "$n" -lt 5 ]; do
    if plasma-apply-wallpaperimage "$wall" >/dev/null 2>&1; then
      log "plasma-apply-wallpaperimage ok: $wall"
      return 0
    fi
    n=$((n + 1))
    sleep 2
  done
  log "plasma-apply-wallpaperimage failed for $wall"
  return 1
}

apply_via_dbus() {
  wall="$1"
  script="
var allDesktops = desktops();
for (i=0;i<allDesktops.length;i++) {
  d = allDesktops[i];
  d.wallpaperPlugin = 'org.kde.image';
  d.currentConfigGroup = Array('Wallpaper', 'org.kde.image', 'General');
  d.writeConfig('Image', 'file://$wall');
}
"
  for q in qdbus6 qdbus-qt6 qdbus qdbus-qt5; do
    if command -v "$q" >/dev/null 2>&1; then
      if "$q" org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript "$script" >/dev/null 2>&1; then
        log "dbus wallpaper via $q ok: $wall"
        return 0
      fi
    fi
  done
  log "dbus wallpaper fallback failed for $wall"
  return 1
}

WALL="$(pick_wall)" || {
  log "no wallpaper asset found"
  exit 0
}

wait_for_plasma || log "plasmashell not detected; attempting apply anyway"

if apply_via_helper "$WALL"; then
  exit 0
fi
apply_via_dbus "$WALL" || true
exit 0
