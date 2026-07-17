#!/usr/bin/env bash
# Build atlas-maps-uk-stub.atlas-pack for ISO / dev installs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist/packs"
STAGE="$OUT/staging-maps-uk"
PACK="$OUT/atlas-maps-uk-stub.atlas-pack"
ISO_PACKS="$ROOT/config/includes.chroot/usr/share/atlas/packs"
PKG_PACKS="$ROOT/packages/atlas-content-manager/usr/share/atlas/packs"

rm -rf "$STAGE"
mkdir -p "$STAGE/payload" "$STAGE/licences" "$STAGE/attribution"

cat > "$STAGE/manifest.json" <<'EOF'
{
  "schema": "atlas.pack/v1",
  "id": "atlas.maps.uk",
  "version": "2026.07",
  "type": "atlas.content.map",
  "name": "United Kingdom Offline Maps",
  "description": "Regional offline maps placeholder for alpha testing.",
  "size_bytes": 1024,
  "minimum_os_version": "0.1.0",
  "architectures": ["all"],
  "mount_target": "/srv/atlas/maps/uk",
  "licences": ["ODbL-1.0"],
  "sources": [],
  "dependencies": [],
  "conflicts": [],
  "post_install_workflow": "maps.reindex",
  "digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000"
}
EOF

echo "Atlas UK maps stub — replace with full tile payload in production." > "$STAGE/payload/README.txt"
echo "Open Database Licence (ODbL) placeholder." > "$STAGE/licences/ODbL.txt"
echo "© OpenStreetMap contributors" > "$STAGE/attribution/OSM.txt"

export ATLAS_ALLOW_UNSIGNED=1
python3 - <<PY
import json, os, sys
from pathlib import Path
sys.path.insert(0, r"$ROOT/packages/atlas-content-manager/usr/lib/atlas")
from content_manager import build_pack
stage = Path(r"$STAGE")
out = Path(r"$PACK")
os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
digest = build_pack(stage, out)
m = json.loads((stage / "manifest.json").read_text())
m["digest"] = digest
(stage / "manifest.json").write_text(json.dumps(m, indent=2))
build_pack(stage, out)
print("Wrote", out, digest)
PY

mkdir -p "$ISO_PACKS" "$PKG_PACKS"
cp -f "$PACK" "$ISO_PACKS/"
cp -f "$PACK" "$PKG_PACKS/"
echo "Staged to $ISO_PACKS and $PKG_PACKS"
