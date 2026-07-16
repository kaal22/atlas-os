#!/usr/bin/env bash
# Phase 2 hybrid ISO: Phase 1 base + Docker + offline OCI/Ollama payload.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Re-executing with sudo (live-build needs root)..."
  exec sudo -E "$0" "$@"
fi

CACHE="${ATLAS_CACHE:-$ROOT/build-cache}"
OUT="$ROOT/dist"
INCLUDES="$ROOT/config/includes.chroot"

echo "=== Phase 2: stage offline payload ==="

# Soft verify if still placeholder; require assets when locked
"$ROOT/scripts/verify-cache.sh" "$ROOT/release/sources.lock.yaml" "$CACHE"

if [[ ! -d "$CACHE/oci" ]] || ! ls "$CACHE/oci"/*.tar >/dev/null 2>&1; then
  echo "ERROR: build-cache/oci is empty. On a networked host run:" >&2
  echo "  make lock-refresh" >&2
  exit 1
fi

# Root-owned leftovers from prior builds
rm -rf "$OUT/payload-stage" "$OUT/payload-user"

"$ROOT/scripts/export-payload.sh" "$OUT" "$CACHE"

# Embed payload + compose into live chroot includes
mkdir -p "$INCLUDES/usr/share/atlas/payload" \
         "$INCLUDES/usr/share/atlas/compose" \
         "$INCLUDES/etc/atlas"
cp -f "$OUT/atlas-core-oci-payload.tar.zst" \
  "$INCLUDES/usr/share/atlas/payload/atlas-core-oci-payload.tar.zst"
cp -f "$ROOT/containers/compose/atlas-core.yml" \
  "$INCLUDES/usr/share/atlas/compose/atlas-core.yml"
# Marker: fail closed on first boot if import fails
: > "$INCLUDES/etc/atlas/payload-enabled"

# Sanity: payload must include images.map (retag on firstboot).
# Avoid `grep -q` in a pipefail pipeline (SIGPIPE makes a successful find look like failure).
payload_list="$(zstd -d -c "$INCLUDES/usr/share/atlas/payload/atlas-core-oci-payload.tar.zst" | tar -t)"
if ! grep -q 'oci/images.map' <<<"$payload_list"; then
  echo "ERROR: payload missing oci/images.map — export-payload is broken" >&2
  echo "$payload_list" | head -30 >&2
  exit 1
fi
echo "OK: payload contains oci/images.map"

# Install Ollama binary into includes (host-native unit already present)
"$ROOT/scripts/install-ollama-from-cache.sh" "$CACHE/ollama" "$INCLUDES"

# Ensure Docker packages are listed
if ! grep -q '^docker.io$' "$ROOT/config/package-lists/atlas.list.chroot"; then
  echo "ERROR: docker.io missing from atlas.list.chroot" >&2
  exit 1
fi

echo "=== Phase 2: invoking full ISO rebuild ==="
export ATLAS_PHASE2=1
exec "$ROOT/scripts/phase1-iso.sh" "$@"
