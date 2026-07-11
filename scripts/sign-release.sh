#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/dist}"
mkdir -p "$OUT"
# Dev signing: write detached .sig placeholders when openssl available
if [[ -f "$ROOT/release/keys/dev/atlas-dev-package.key" ]]; then
  for f in "$OUT"/*.{iso,zst,json}; do
    [[ -f "$f" ]] || continue
    openssl dgst -sha256 -sign "$ROOT/release/keys/dev/atlas-dev-package.key" -out "$f.sig" "$f" || true
  done
else
  echo "No dev private key — run scripts/generate-dev-keys.sh; writing unsigned markers"
  for f in "$OUT"/*.iso; do
    [[ -f "$f" ]] || continue
    echo "UNSIGNED" > "$f.sig"
  done
fi
echo "Sign pass complete for $OUT"
