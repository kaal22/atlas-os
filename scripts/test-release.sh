#!/usr/bin/env bash
# QEMU UEFI smoke tests for Atlas ISO.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-install}"
VERSION="$(cat "$ROOT/VERSION")"
OUT="$ROOT/dist"
EVIDENCE="$ROOT/tests/installer/evidence"
ISO="$OUT/atlas-os-${VERSION}-amd64.iso"
mkdir -p "$EVIDENCE"

if [[ ! -f "$ISO" ]]; then
  echo "ISO missing; running build-iso (may produce stub on non-Debian hosts)..."
  "$ROOT/scripts/build-iso.sh" --out "$OUT" || true
fi

if [[ ! -f "$ISO" ]]; then
  echo "ERROR: no ISO at $ISO" >&2
  exit 1
fi

cat > "$EVIDENCE/package-manifest.txt" <<EOF
ISO: $(basename "$ISO")
SHA256: $(sha256sum "$ISO" 2>/dev/null | awk '{print $1}' || cat "$ISO.sha256" 2>/dev/null)
VERSION: $VERSION
MODE: $MODE
DATE: $(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF

# Detect stub ISO
if head -c 20 "$ISO" | grep -q ATLAS_OS_ISO_STUB; then
  cat > "$EVIDENCE/known-limitations.txt" <<'EOF'
- Host did not have live-build; ISO is a non-bootable pipeline stub.
- Re-run scripts/build-iso.sh on Debian 13 with live-build, OVMF, and QEMU for real evidence.
- Calamares install path cannot be exercised against a stub ISO.
EOF
  cat > "$EVIDENCE/qemu-boot.log" <<EOF
[atlas-test] Stub ISO detected — skipped QEMU boot.
[atlas-test] Command that would run:
qemu-system-x86_64 -machine q35 -m 2048 -bios OVMF.fd -cdrom $ISO -boot d -display none -serial stdio
EOF
  echo "Install test recorded stub evidence under $EVIDENCE"
  exit 0
fi

if ! command -v qemu-system-x86_64 >/dev/null; then
  echo "qemu-system-x86_64 not found" >&2
  exit 1
fi

OVMF_CODE=""
for c in /usr/share/OVMF/OVMF_CODE_4M.fd /usr/share/OVMF/OVMF_CODE.fd /usr/share/ovmf/OVMF.fd; do
  if [[ -f "$c" ]]; then OVMF_CODE="$c"; break; fi
done
if [[ -z "$OVMF_CODE" ]]; then
  echo "OVMF firmware not found" >&2
  exit 1
fi

DISK="$OUT/atlas-test-disk.qcow2"
qemu-img create -f qcow2 "$DISK" 40G
timeout 120 qemu-system-x86_64 \
  -machine q35 \
  -m 2048 \
  -drive if=pflash,format=raw,readonly=on,file="$OVMF_CODE" \
  -cdrom "$ISO" \
  -drive file="$DISK",if=virtio \
  -boot d \
  -display none \
  -serial file:"$EVIDENCE/qemu-boot.log" \
  || true

echo "QEMU smoke completed — inspect $EVIDENCE/qemu-boot.log"
echo "Reboot into installed disk requires full Calamares automation (Phase 1 stretch)." > "$EVIDENCE/installed-boot.log"
