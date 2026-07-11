#!/usr/bin/env bash
# Full clean Phase 1 hybrid ISO rebuild (Debian 13 + live-build).
# Produces a normal-style USB image:
#   - Install Atlas OS  (default — live session + Calamares)
#   - Try Atlas OS      (live desktop only)
#   - UEFI GRUB + BIOS isolinux hybrid boot
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Re-executing with sudo (live-build needs root)..."
  exec sudo -E "$0" "$@"
fi

export DEBIAN_FRONTEND=noninteractive

if ! command -v lb >/dev/null 2>&1; then
  echo "Installing live-build and ISO tooling..."
  "$ROOT/scripts/install-build-deps.sh"
fi

# Ensure hybrid boot tooling is present on the build host
apt-get install -y \
  live-build debootstrap squashfs-tools xorriso isolinux syslinux-utils \
  grub-efi-amd64-bin grub-pc-bin mtools dosfstools dpkg-dev \
  apt-utils >/dev/null

VERSION="$(cat "$ROOT/VERSION")"
OUT="$ROOT/dist"
ISO="$OUT/atlas-os-${VERSION}-amd64.iso"

echo "=== Full clean Phase 1 rebuild ==="
echo "Version: $VERSION"
echo "This removes chroot/, binary/, .build/ and rebuilds from scratch."
echo

# Purge previous live-build tree so GRUB/EFI/isolinux are regenerated cleanly
lb clean --purge || true
rm -rf "$ROOT/chroot" "$ROOT/binary" "$ROOT/.build" \
  "$ROOT"/live-image-*.iso "$ROOT"/*.hybrid.iso \
  "$ROOT/cache/bootstrap" 2>/dev/null || true
# Keep apt package cache under cache/packages.* to speed downloads if present

mkdir -p "$OUT"

# Stage conflicting GRUB meta .debs for offline Calamares (BIOS vs UEFI target)
"$ROOT/scripts/stage-grub-installer-debs.sh" \
  "$ROOT/config/includes.chroot/usr/share/atlas/installer-debs"

# Fresh local Atlas debs for packages.chroot (live-build indexes them itself)
"$ROOT/scripts/build-debs.sh" "$OUT/debs"
rm -rf "$ROOT/config/packages.chroot"
mkdir -p "$ROOT/config/packages.chroot"
cp "$OUT/debs"/atlas-*.deb "$ROOT/config/packages.chroot/"
# Do not pre-seed Packages / packages.list — that breaks lb binary apt order.

mkdir -p "$ROOT/config/includes.chroot/usr/share/atlas"
cp -a "$ROOT/calamares" "$ROOT/config/includes.chroot/usr/share/atlas/"

chmod +x "$ROOT/auto/"* \
  "$ROOT/config/hooks/normal/"*.hook.chroot \
  "$ROOT/config/hooks/live/"*.hook.chroot \
  "$ROOT/config/hooks/normal/"*.hook.binary 2>/dev/null || true

echo "=== lb config + lb build (full) ==="
lb config
lb build

mkdir -p "$OUT"
shopt -s nullglob
found=0
for f in live-image-*.hybrid.iso live-image-*.iso *.hybrid.iso; do
  [[ -f "$f" ]] || continue
  if head -c 20 "$f" 2>/dev/null | grep -q ATLAS_OS_ISO_STUB; then
    continue
  fi
  mv -f "$f" "$ISO"
  (cd "$OUT" && sha256sum "$(basename "$ISO")" | tee "$(basename "$ISO").sha256")
  (cd "$OUT" && sha512sum "$(basename "$ISO")" | tee "$(basename "$ISO").sha512")
  found=1
done

if [[ "$found" -eq 0 ]]; then
  echo "ERROR: no hybrid ISO produced. See $ROOT/build.log" >&2
  exit 1
fi

echo
echo "=== Boot menu (GRUB) ==="
if [[ -f "$ROOT/binary/boot/grub/grub.cfg" ]]; then
  head -30 "$ROOT/binary/boot/grub/grub.cfg"
else
  echo "WARNING: binary/boot/grub/grub.cfg missing after build" >&2
fi

echo
echo "=== EFI / isolinux ==="
ls -la "$ROOT/binary/EFI" 2>/dev/null | head -10 || echo "WARNING: no EFI dir"
ls -la "$ROOT/binary/isolinux/isolinux.bin" 2>/dev/null || echo "WARNING: no isolinux.bin"
ls -la "$ROOT/binary/boot/grub/efi.img" 2>/dev/null || echo "WARNING: no efi.img"

echo
echo "OK: $ISO"
ls -lh "$ISO"
sha256sum "$ISO"
echo
echo "USB flash example:"
echo "  sudo dd if=$ISO of=/dev/sdX bs=4M status=progress oflag=sync"
echo
echo "Boot menu:"
echo "  Install Atlas OS  — default, opens Calamares after live desktop starts"
echo "  Try Atlas OS      — live desktop only (no installer autostart)"
