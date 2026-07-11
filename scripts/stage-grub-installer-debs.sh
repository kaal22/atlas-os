#!/usr/bin/env bash
# Download GRUB meta-packages for offline Calamares target install.
# These conflict with each other so they must NOT be installed into the live
# chroot — only staged for dpkg -i onto the installed system.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/config/includes.chroot/usr/share/atlas/installer-debs}"
mkdir -p "$OUT"

export DEBIAN_FRONTEND=noninteractive
if ! command -v apt-get >/dev/null; then
  echo "apt-get required" >&2
  exit 1
fi

tmpdir="$(mktemp -d)"
cleanup() { rm -rf "$tmpdir"; }
trap cleanup EXIT

cd "$tmpdir"
apt-get download grub-pc grub-efi-amd64
cp -f grub-pc_*.deb grub-efi-amd64_*.deb "$OUT/"
echo "Staged GRUB meta-packages in $OUT:"
ls -lh "$OUT"/grub-*.deb
