#!/usr/bin/env bash
# Fast remaster: inject installer into existing chroot, then rebuild ISO.
# Avoids the live-build trap where chroot_apt runs before Packages is regenerated.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VERSION="$(cat VERSION)"
OUT="$ROOT/dist"
ISO_NAME="atlas-os-${VERSION}-amd64.iso"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Re-executing with sudo..."
  exec sudo -E "$0" "$@"
fi

if [[ ! -d "$ROOT/chroot/usr" ]]; then
  echo "ERROR: no chroot/ found. Run ./scripts/phase1-iso.sh first." >&2
  exit 1
fi

echo "=== Sync Atlas debs into config/packages.chroot ==="
mkdir -p "$OUT/debs" "$ROOT/config/packages.chroot"
if [[ ! -f "$OUT/debs/atlas-shell_0.1.0-1_all.deb" ]]; then
  "$ROOT/scripts/build-debs.sh" "$OUT/debs"
fi
rm -f "$ROOT/config/packages.chroot"/atlas-*.deb
cp "$OUT/debs"/atlas-*.deb "$ROOT/config/packages.chroot/"
# Do NOT put a Packages index here — live-build chroot_archives generates it
# inside the chroot at the correct time. Stale packages.list without Packages
# makes lb binary fail during early apt update.

echo "=== Inject Install Atlas OS launcher into chroot ==="
install -d \
  "$ROOT/chroot/usr/bin" \
  "$ROOT/chroot/usr/lib/atlas" \
  "$ROOT/chroot/usr/share/applications" \
  "$ROOT/chroot/etc/skel/Desktop" \
  "$ROOT/chroot/etc/xdg/autostart" \
  "$ROOT/chroot/usr/share/calamares/branding" \
  "$ROOT/chroot/etc/calamares/branding"

cat > "$ROOT/chroot/usr/bin/atlas-install" <<'EOF'
#!/bin/sh
exec /usr/bin/calamares-install-debian "$@"
EOF
chmod 755 "$ROOT/chroot/usr/bin/atlas-install"

cat > "$ROOT/chroot/usr/share/applications/calamares-install-debian.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Version=1.0
Name=Install Atlas OS
GenericName=Atlas OS Installer
Exec=atlas-install
Comment=Install Atlas OS on this computer
Keywords=calamares;system;install;atlas;installer
Icon=system-software-install
Terminal=false
Categories=Qt;System;
StartupWMClass=calamares
StartupNotify=true
EOF
cp -f "$ROOT/chroot/usr/share/applications/calamares-install-debian.desktop" \
  "$ROOT/chroot/usr/share/applications/install-atlas-os.desktop"
cp -f "$ROOT/chroot/usr/share/applications/install-atlas-os.desktop" \
  "$ROOT/chroot/etc/skel/Desktop/install-atlas-os.desktop"
chmod 755 "$ROOT/chroot/etc/skel/Desktop/install-atlas-os.desktop"

cat > "$ROOT/chroot/usr/lib/atlas/maybe-autostart-installer.sh" <<'EOF'
#!/bin/sh
set -e
if ! grep -qw atlas-install /proc/cmdline 2>/dev/null; then
  exit 0
fi
i=0
while [ "$i" -lt 60 ]; do
  if [ -n "${DISPLAY:-}" ] || [ -n "${WAYLAND_DISPLAY:-}" ]; then
    break
  fi
  if [ -S /tmp/.X11-unix/X0 ] || [ -S /tmp/.X11-unix/X1 ]; then
    export DISPLAY="${DISPLAY:-:0}"
    break
  fi
  i=$((i + 1))
  sleep 1
done
sleep 2
export QT_AUTO_SCREEN_SCALE_FACTOR="${QT_AUTO_SCREEN_SCALE_FACTOR:-1}"
if command -v atlas-install >/dev/null 2>&1; then
  exec atlas-install
fi
exec calamares-install-debian
EOF
chmod 755 "$ROOT/chroot/usr/lib/atlas/maybe-autostart-installer.sh"

cat > "$ROOT/chroot/etc/xdg/autostart/atlas-install-autostart.desktop" <<'EOF'
[Desktop Entry]
Type=Application
Name=Atlas Install Autostart
Exec=/usr/lib/atlas/maybe-autostart-installer.sh
Terminal=false
NoDisplay=true
X-KDE-autostart-phase=2
X-KDE-autostart-after=panel
OnlyShowIn=KDE;GNOME;XFCE;LXDE;LXQt;MATE;Cinnamon;
EOF

if [[ -d "$ROOT/calamares/branding/atlas" ]]; then
  cp -a "$ROOT/calamares/branding/atlas" "$ROOT/chroot/usr/share/calamares/branding/"
  cp -a "$ROOT/calamares/branding/atlas" "$ROOT/chroot/etc/calamares/branding/"
fi
if [[ -f "$ROOT/calamares/settings.conf" ]]; then
  cp "$ROOT/calamares/settings.conf" "$ROOT/chroot/etc/calamares/settings.conf"
fi

echo "=== Sanitize chroot apt before lb binary ==="
# live-build order: chroot_apt update runs BEFORE chroot_archives regenerates
# file:/packages. Any leftover packages.list without Packages.gz hard-fails.
rm -f "$ROOT/chroot/etc/apt/sources.list.d/packages.list"
rm -rf "$ROOT/chroot/packages"
rm -f "$ROOT/chroot/var/lib/apt/lists"/_packages_* \
      "$ROOT/chroot/var/lib/apt/lists"/Partial/_packages_* 2>/dev/null || true

# Restore primary sources.list if live-build had moved it aside
if [[ -f "$ROOT/chroot/etc/apt/sources.list.d/zz-sources.list" ]]; then
  if [[ ! -f "$ROOT/chroot/etc/apt/sources.list" ]]; then
    mv "$ROOT/chroot/etc/apt/sources.list.d/zz-sources.list" \
      "$ROOT/chroot/etc/apt/sources.list"
  else
    rm -f "$ROOT/chroot/etc/apt/sources.list.d/zz-sources.list"
  fi
fi

if [[ ! -f "$ROOT/chroot/etc/apt/sources.list" ]]; then
  cat > "$ROOT/chroot/etc/apt/sources.list" <<'EOF'
deb http://deb.debian.org/debian/ trixie main contrib non-free non-free-firmware
deb http://security.debian.org/ trixie-security main contrib non-free non-free-firmware
deb http://deb.debian.org/debian/ trixie-updates main contrib non-free non-free-firmware
EOF
fi

echo "=== Rebuild binary/ISO ==="
if [[ ! -e "$ROOT/config/bootstrap" ]]; then
  lb config
fi

lb clean --binary
# Re-assert sanitize after clean (belt and braces)
rm -f "$ROOT/chroot/etc/apt/sources.list.d/packages.list"
rm -rf "$ROOT/chroot/packages"

lb binary

mkdir -p "$OUT"
shopt -s nullglob
found=0
for f in live-image-*.hybrid.iso live-image-*.iso *.hybrid.iso; do
  [[ -f "$f" ]] || continue
  if head -c 20 "$f" 2>/dev/null | grep -q ATLAS_OS_ISO_STUB; then
    continue
  fi
  mv -f "$f" "$OUT/$ISO_NAME"
  (cd "$OUT" && sha256sum "$ISO_NAME" | tee "${ISO_NAME}.sha256")
  found=1
done

if [[ "$found" -eq 0 ]]; then
  newest="$(find . -maxdepth 2 -type f \( -name '*.hybrid.iso' -o -name 'live-image-*.iso' \) -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2- || true)"
  if [[ -n "${newest:-}" && -f "$newest" ]]; then
    cp -f "$newest" "$OUT/$ISO_NAME"
    (cd "$OUT" && sha256sum "$ISO_NAME" | tee "${ISO_NAME}.sha256")
    found=1
  fi
fi

if [[ "$found" -eq 0 ]]; then
  echo "ERROR: ISO not produced." >&2
  exit 1
fi

echo
echo "=== Boot menu check ==="
if [[ -f "$ROOT/binary/boot/grub/grub.cfg" ]]; then
  head -25 "$ROOT/binary/boot/grub/grub.cfg"
else
  echo "(grub.cfg missing — check build.log)"
fi

echo
echo "OK: $OUT/$ISO_NAME"
ls -lh "$OUT/$ISO_NAME"
echo "Default USB boot entry should be: Install Atlas OS"
