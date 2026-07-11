#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/dist}"
mkdir -p "$OUT"
# Export compose + scripts into a payload staging dir (OCI tars come from cache)
STAGE="$OUT/payload-stage"
rm -rf "$STAGE"
mkdir -p "$STAGE/compose" "$STAGE/scripts"
cp "$ROOT/containers/compose/atlas-core.yml" "$STAGE/compose/"
cp "$ROOT/packages/atlas-firstboot/usr/lib/atlas/import-payload.sh" "$STAGE/scripts/"
if [[ -d "$ROOT/build-cache/oci" ]] && ls "$ROOT/build-cache/oci"/*.tar >/dev/null 2>&1; then
  mkdir -p "$STAGE/oci"
  cp "$ROOT/build-cache/oci"/*.tar "$STAGE/oci/" || true
  tar --zstd -cf "$OUT/atlas-core-oci-payload.tar.zst" -C "$STAGE" .
  (cd "$OUT" && sha256sum atlas-core-oci-payload.tar.zst | tee atlas-core-oci-payload.tar.zst.sha256)
else
  echo "No OCI tars in build-cache/oci — wrote compose staging only."
  tar --zstd -cf "$OUT/atlas-core-compose-bundle.tar.zst" -C "$STAGE" .
fi
echo "Payload export done."
