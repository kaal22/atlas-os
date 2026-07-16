#!/usr/bin/env bash
# Export compose + OCI docker-archives into a compressed payload for the ISO.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/dist}"
CACHE="${2:-$ROOT/build-cache}"
mkdir -p "$OUT"

STAGE="$OUT/payload-stage"
rm -rf "$STAGE"
mkdir -p "$STAGE/compose" "$STAGE/scripts" "$STAGE/oci"

cp "$ROOT/containers/compose/atlas-core.yml" "$STAGE/compose/"
cp "$ROOT/packages/atlas-firstboot/usr/lib/atlas/import-payload.sh" "$STAGE/scripts/"

# Map archive filenames -> docker image refs (archives may have empty RepoTags).
cat > "$STAGE/oci/images.map" <<'EOF'
# archive_basename<TAB_OR_SPACE>image_ref
mysql_8.0.tar mysql:8.0
redis_7-alpine.tar redis:7-alpine
qdrant_qdrant_v1.16.tar qdrant/qdrant:v1.16
ghcr.io_kiwix_kiwix-serve_3.8.2.tar ghcr.io/kiwix/kiwix-serve:3.8.2
treehouses_kolibri_0.12.8.tar treehouses/kolibri:0.12.8
ghcr.io_gchq_cyberchef_10.24.tar ghcr.io/gchq/cyberchef:10.24
dullage_flatnotes_v5.5.4.tar dullage/flatnotes:v5.5.4
ghcr.io_crosstalk-solutions_project-nomad_v1.33.0.tar ghcr.io/crosstalk-solutions/project-nomad:v1.33.0
EOF

if [[ -d "$CACHE/oci" ]] && ls "$CACHE/oci"/*.tar >/dev/null 2>&1; then
  cp "$CACHE/oci"/*.tar "$STAGE/oci/"
  tar --zstd -cf "$OUT/atlas-core-oci-payload.tar.zst" -C "$STAGE" .
  (cd "$OUT" && sha256sum atlas-core-oci-payload.tar.zst | tee atlas-core-oci-payload.tar.zst.sha256)
  echo "Payload export done: $OUT/atlas-core-oci-payload.tar.zst"
else
  echo "ERROR: No OCI tars in $CACHE/oci — run make lock-refresh first" >&2
  tar --zstd -cf "$OUT/atlas-core-compose-bundle.tar.zst" -C "$STAGE" .
  exit 1
fi
