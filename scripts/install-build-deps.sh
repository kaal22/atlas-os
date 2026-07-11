#!/usr/bin/env bash
set -euo pipefail
# Install packages required on a Debian 13 build host.
export DEBIAN_FRONTEND=noninteractive
if ! command -v apt-get >/dev/null; then
  echo "This script expects a Debian-family host." >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y \
  live-build \
  debootstrap \
  squashfs-tools \
  xorriso \
  isolinux \
  syslinux-utils \
  grub-efi-amd64-bin \
  grub-pc-bin \
  mtools \
  dosfstools \
  rsync \
  git \
  make \
  python3 \
  python3-yaml \
  skopeo \
  jq \
  qemu-system-x86 \
  ovmf \
  dpkg-dev \
  debhelper \
  fakeroot \
  curl \
  ca-certificates \
  zstd
echo "Build dependencies installed."
