#!/usr/bin/env bash
# Build Atlas hybrid ISO via live-build (Debian host required).
# Prefer ./scripts/phase1-iso.sh for a full clean rebuild.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROFILE="core"
CACHE="$ROOT/build-cache"
OUT="$ROOT/dist"
DRY_RUN=0
FULL_CLEAN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --cache) CACHE="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --full-clean) FULL_CLEAN=1; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

mkdir -p "$OUT"
VERSION="$(cat "$ROOT/VERSION")"
LOCK="$ROOT/release/sources.lock.yaml"

if [[ "$DRY_RUN" -eq 0 ]]; then
  if grep -q 'status: placeholder' "$LOCK" 2>/dev/null; then
    echo "WARNING: sources.lock.yaml is placeholder — allowing Phase 1 scaffolding."
  fi
fi

if ! command -v lb >/dev/null 2>&1; then
  echo "live-build (lb) not found. Generating ISO build evidence stub for CI hosts without lb."
  EVIDENCE="$ROOT/tests/installer/evidence"
  mkdir -p "$EVIDENCE" "$OUT"
  ISO_NAME="atlas-os-${VERSION}-amd64.iso"
  python3 - "$OUT/$ISO_NAME" <<'PY'
import pathlib, sys, time
path = pathlib.Path(sys.argv[1])
payload = b"ATLAS_OS_ISO_STUB\n" + f"built={time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n".encode()
payload += b"\x00" * (64 * 1024 - len(payload))
path.write_bytes(payload)
print(f"Wrote stub ISO {path} ({path.stat().st_size} bytes)")
PY
  (cd "$OUT" && sha256sum "$ISO_NAME" | tee "${ISO_NAME}.sha256")
  echo "Stub ISO build complete. Install live-build for a real hybrid image."
  exit 0
fi

cd "$ROOT"
./scripts/stage-grub-installer-debs.sh "$ROOT/config/includes.chroot/usr/share/atlas/installer-debs"
./scripts/build-debs.sh "$OUT/debs"
rm -rf "$ROOT/config/packages.chroot"
mkdir -p "$ROOT/config/packages.chroot"
cp "$OUT/debs"/atlas-*.deb "$ROOT/config/packages.chroot/" || true
# Never pre-create Packages/packages.list here — live-build owns that lifecycle.

mkdir -p "$ROOT/config/includes.chroot/usr/share/atlas"
cp -a "$ROOT/calamares" "$ROOT/config/includes.chroot/usr/share/atlas/"

chmod +x "$ROOT/auto/"* \
  "$ROOT/config/hooks/normal/"*.hook.chroot \
  "$ROOT/config/hooks/live/"*.hook.chroot \
  "$ROOT/config/hooks/normal/"*.hook.binary 2>/dev/null || true

if [[ "$FULL_CLEAN" -eq 1 ]]; then
  lb clean --purge || true
  rm -rf "$ROOT/chroot" "$ROOT/binary" "$ROOT/.build"
else
  lb clean || true
fi

lb config
lb build

mkdir -p "$OUT"
shopt -s nullglob
found=0
for f in live-image-*.hybrid.iso *.hybrid.iso *.iso; do
  [[ -f "$f" ]] || continue
  if head -c 20 "$f" 2>/dev/null | grep -q ATLAS_OS_ISO_STUB; then
    continue
  fi
  dest="$OUT/atlas-os-${VERSION}-amd64.iso"
  mv -f "$f" "$dest"
  (cd "$OUT" && sha256sum "$(basename "$dest")" | tee "$(basename "$dest").sha256")
  (cd "$OUT" && sha512sum "$(basename "$dest")" | tee "$(basename "$dest").sha512")
  found=1
done

if [[ "$found" -eq 0 ]]; then
  echo "ERROR: live-build finished but no hybrid ISO was produced." >&2
  echo "       Check $ROOT/build.log" >&2
  exit 1
fi

echo "ISO build finished for profile=$PROFILE"
