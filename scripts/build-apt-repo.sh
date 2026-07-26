#!/usr/bin/env bash
# Build a small local APT repository of Atlas .deb packages.
#
# Usage:
#   ./scripts/build-debs.sh                 # produce dist/debs/*.deb
#   ./scripts/build-apt-repo.sh             # → dist/apt-repo (+ optional USB staging)
#
# Signing (optional, never commit private keys):
#   ATLAS_APT_GPG_KEY=KEYID ./scripts/build-apt-repo.sh
#   # or: ATLAS_APT_GPG_KEYRING=/path/to/secring-or-homedir …
#
# Offline/USB: copy dist/apt-repo to a stick as atlas-apt-repo/, then on device:
#   sudo python3 /usr/lib/atlas/atlas-os-apt.py enable-source /media/…/atlas-apt-repo
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEB_DIR="${1:-$ROOT/dist/debs}"
OUT="${2:-$ROOT/dist/apt-repo}"
SUITE="${ATLAS_APT_SUITE:-atlas}"
COMPONENT="${ATLAS_APT_COMPONENT:-main}"
ARCHS="${ATLAS_APT_ARCHS:-all}"

mkdir -p "$OUT/pool/$COMPONENT" "$OUT/dists/$SUITE/$COMPONENT/binary-all"

shopt -s nullglob
debs=("$DEB_DIR"/*.deb)
if ((${#debs[@]} == 0)); then
  echo "No .deb files in $DEB_DIR — run ./scripts/build-debs.sh first." >&2
  exit 1
fi

echo "Staging ${#debs[@]} packages into $OUT"
for deb in "${debs[@]}"; do
  base="$(basename "$deb")"
  # Prefer atlas-* only for the phase-1 product repo; still allow explicit override.
  if [[ "${ATLAS_APT_INCLUDE_ALL:-0}" != "1" && "$base" != atlas-* ]]; then
    echo "  skip non-atlas: $base"
    continue
  fi
  cp -a "$deb" "$OUT/pool/$COMPONENT/"
done

POOL_DEB=("$OUT/pool/$COMPONENT"/atlas-*.deb)
if ((${#POOL_DEB[@]} == 0)); then
  echo "No atlas-*.deb staged." >&2
  exit 1
fi

BIN_DIR="$OUT/dists/$SUITE/$COMPONENT/binary-all"
if command -v apt-ftparchive >/dev/null 2>&1; then
  apt-ftparchive packages "$OUT/pool/$COMPONENT" > "$BIN_DIR/Packages"
  gzip -9c "$BIN_DIR/Packages" > "$BIN_DIR/Packages.gz"
  apt-ftparchive \
    -o "APT::FTPArchive::Release::Origin=Arcalium OS" \
    -o "APT::FTPArchive::Release::Label=Atlas" \
    -o "APT::FTPArchive::Release::Suite=$SUITE" \
    -o "APT::FTPArchive::Release::Codename=$SUITE" \
    -o "APT::FTPArchive::Release::Architectures=$ARCHS" \
    -o "APT::FTPArchive::Release::Components=$COMPONENT" \
    release "$OUT/dists/$SUITE" > "$OUT/dists/$SUITE/Release"
else
  echo "apt-ftparchive not found; writing minimal Packages listing" >&2
  : > "$BIN_DIR/Packages"
  for deb in "${POOL_DEB[@]}"; do
    python3 - "$deb" >> "$BIN_DIR/Packages" <<'PY'
import hashlib, sys
from pathlib import Path
p = Path(sys.argv[1])
# Minimal stanza so file:// apt can see the package name/version when dpkg-deb exists.
import subprocess
ctrl = subprocess.check_output(["dpkg-deb", "-f", str(p), "Package", "Version", "Architecture", "Depends", "Maintainer", "Description"], text=True)
size = p.stat().st_size
sha = hashlib.sha256(p.read_bytes()).hexdigest()
rel = f"pool/main/{p.name}"
print(ctrl.rstrip())
print(f"Filename: {rel}")
print(f"Size: {size}")
print(f"SHA256: {sha}")
print()
PY
  done
  gzip -9c "$BIN_DIR/Packages" > "$BIN_DIR/Packages.gz"
  cat > "$OUT/dists/$SUITE/Release" <<EOF
Origin: Arcalium OS
Label: Atlas
Suite: $SUITE
Codename: $SUITE
Architectures: $ARCHS
Components: $COMPONENT
Date: $(date -Ru)
EOF
fi

# Optional GPG detach-sign / InRelease (ceremony key — not invented in-tree).
if [[ -n "${ATLAS_APT_GPG_KEY:-}" ]] && command -v gpg >/dev/null 2>&1; then
  echo "Signing Release with GPG key $ATLAS_APT_GPG_KEY"
  gpg --batch --yes --default-key "$ATLAS_APT_GPG_KEY" \
    --armor --detach-sign -o "$OUT/dists/$SUITE/Release.gpg" "$OUT/dists/$SUITE/Release"
  gpg --batch --yes --default-key "$ATLAS_APT_GPG_KEY" \
    --clearsign -o "$OUT/dists/$SUITE/InRelease" "$OUT/dists/$SUITE/Release"
else
  echo "Unsigned Release (set ATLAS_APT_GPG_KEY to sign). Dev/USB may use [trusted=yes]."
fi

# Convenience copy path for packaging into images / USB docs
STAGE_SHARE="$ROOT/packages/atlas-updater/usr/share/atlas/apt-repo-README.txt"
cat > "$STAGE_SHARE" <<EOF
Copy the built tree from dist/apt-repo onto the appliance as /srv/atlas/apt-repo
or onto USB as atlas-apt-repo/, then enable with atlas-os-apt.py enable-source.
Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Packages: ${#POOL_DEB[@]}
EOF

echo "OK apt repo at $OUT (suite=$SUITE component=$COMPONENT)"
ls -la "$OUT/pool/$COMPONENT" | head -40
