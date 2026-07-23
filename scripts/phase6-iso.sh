#!/usr/bin/env bash
# Phase 6 ISO: content packs + catalogue (maps stub on ISO).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Phase 6: content and models ==="
echo "Ensures content manager, catalogue, stub pack, and CC Content UI are present,"
echo "then invokes phase5-iso.sh (knowledge/RAG + phase4 agent runtime)."
echo

for need in \
  packages/atlas-content-manager/usr/lib/atlas/content_manager.py \
  packages/atlas-content-manager/usr/share/atlas/catalogue.json \
  packages/atlas-command-centre/usr/lib/atlas/command_centre.py
do
  if [[ ! -f "$ROOT/$need" ]]; then
    echo "ERROR: missing $need" >&2
    exit 1
  fi
done

if ! grep -q 'def install_pack' "$ROOT/packages/atlas-content-manager/usr/lib/atlas/content_manager.py"; then
  echo "ERROR: content_manager.py missing install_pack" >&2
  exit 1
fi
if ! grep -q '/api/content/catalogue' "$ROOT/packages/atlas-command-centre/usr/lib/atlas/command_centre.py"; then
  echo "ERROR: command_centre.py missing Content API routes" >&2
  exit 1
fi

echo "=== Building content packs (maps + knowledge) ==="
"$ROOT/scripts/build-content-packs.sh"

mkdir -p "$ROOT/config/includes.chroot/usr/share/atlas"
cp -f "$ROOT/packages/atlas-content-manager/usr/share/atlas/catalogue.json" \
  "$ROOT/config/includes.chroot/usr/share/atlas/catalogue.json"

if [[ ! -f "$ROOT/config/includes.chroot/usr/share/atlas/packs/atlas-maps-uk-stub.atlas-pack" ]]; then
  echo "ERROR: stub pack not staged in includes" >&2
  exit 1
fi

export ATLAS_PHASE6=1
exec "$ROOT/scripts/phase5-iso.sh" "$@"
