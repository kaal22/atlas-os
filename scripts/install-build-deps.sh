#!/usr/bin/env bash
set -euo pipefail
# Install packages required on a Debian 13 build host.
export DEBIAN_FRONTEND=noninteractive
if ! command -v apt-get >/dev/null; then
  echo "This script expects a Debian-family host." >&2
  exit 1
fi
APT=(apt-get)
if [[ "$(id -u)" -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    APT=(sudo apt-get)
  else
    echo "ERROR: root or sudo required to install packages." >&2
    exit 1
  fi
fi
"${APT[@]}" update
"${APT[@]}" install -y \
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
