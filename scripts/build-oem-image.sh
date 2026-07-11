#!/usr/bin/env bash
# Build OEM disk image from installed system or golden chroot (Phase 8).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${2:-$ROOT/dist}"
CACHE="${1:-$ROOT/build-cache}"
mkdir -p "$OUT"
VERSION="$(cat "$ROOT/VERSION")"
IMG="$OUT/atlas-os-${VERSION}-oem-amd64.img"
# Compact placeholder for pipeline wiring (real OEM uses virt-make-fs of golden disk)
python3 - <<PY
from pathlib import Path
p = Path(r"$IMG")
header = b"ATLAS_OS_OEM_IMG\n"
p.write_bytes(header + b"\0" * (1024 * 1024 - len(header)))
print("Wrote OEM placeholder", p, p.stat().st_size)
PY
if command -v zstd >/dev/null; then
  zstd -f -o "${IMG}.zst" "$IMG"
  (cd "$OUT" && sha256sum "$(basename "$IMG").zst" | tee "$(basename "$IMG").zst.sha256")
fi
cat > "$OUT/oem-qc-mode.md" <<'EOF'
# OEM QC mode

1. Boot golden image.
2. Run `atlas-qc --self-test`.
3. Verify first-boot pending flag.
4. Seal image (clear machine-id, unique secrets regenerate on customer first boot).
EOF
echo "OEM image artefacts in $OUT"
