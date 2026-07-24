#!/usr/bin/env bash
# Download a country PMTiles extract for Atlas offline maps.
#
# Default source: Protomaps daily basemap (ODbL — © OpenStreetMap contributors)
# via `pmtiles extract` over HTTP range requests (does NOT download the full planet).
#
# Usage:
#   ./scripts/fetch-country-pmtiles.sh uk
#   ATLAS_MAP_CC=de ./scripts/fetch-country-pmtiles.sh
#   ATLAS_PMTILES_URL='https://example/uk.pmtiles' ./scripts/fetch-country-pmtiles.sh uk
#   ATLAS_PMTILES_PLANET_URL='https://build.protomaps.com/20260721.pmtiles' \
#     ATLAS_PMTILES_MAXZOOM=10 ./scripts/fetch-country-pmtiles.sh ie
#
# Output (build tree, like Wikipedia ZIM):
#   content/packs/maps/<cc>/<cc>.pmtiles
# Then rebuild packs (optional — embeds tiles into .atlas-pack):
#   ./scripts/build-content-packs.sh --maps-only
#
# Runtime install (Command Centre / content manager) can also fetch directly into
# /srv/atlas/maps/<cc>/ without rebuilding the pack.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CM_PY="$ROOT/packages/atlas-content-manager/usr/lib/atlas"
COUNTRIES_JSON="$ROOT/content/packs/maps/countries.json"

CC="${1:-${ATLAS_MAP_CC:-}}"
CC="$(echo "$CC" | tr '[:upper:]' '[:lower:]')"

if [[ -z "$CC" ]]; then
  cat <<EOF
Usage: $0 <country-code>

Country codes are listed in content/packs/maps/countries.json
(e.g. uk, us, de, fr, ie, za, in).

Environment:
  ATLAS_PMTILES_URL         Direct .pmtiles URL (skips Protomaps extract)
  ATLAS_PMTILES_PLANET_URL  Protomaps planet archive for extract
  ATLAS_PMTILES_MAXZOOM     Max zoom (default from countries.json / 12; each level ~2x size)
  ATLAS_MAPS_DEST           Override output directory

Licence: ODbL-1.0 — © OpenStreetMap contributors (Protomaps basemap).
Large countries (us, ca, br, in, au) stay at maxzoom 11 unless you raise
ATLAS_PMTILES_MAXZOOM — each level roughly doubles size.
EOF
  exit 1
fi

DEST_DIR="${ATLAS_MAPS_DEST:-$ROOT/content/packs/maps/$CC}"
mkdir -p "$DEST_DIR"

export PYTHONPATH="$CM_PY${PYTHONPATH:+:$PYTHONPATH}"
export ATLAS_ALLOW_UNSIGNED="${ATLAS_ALLOW_UNSIGNED:-1}"

python3 - <<PY
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, r"$CM_PY")
from content_manager import PackError, fetch_country_pmtiles, resolve_country_meta

cc = "$CC"
dest = Path(r"$DEST_DIR")
countries = json.loads(Path(r"$COUNTRIES_JSON").read_text(encoding="utf-8"))
defaults = countries.get("tiles_defaults") or {}
meta = resolve_country_meta(cc, countries)
if not meta:
    print(f"Unknown country code: {cc}", file=sys.stderr)
    sys.exit(1)

hint = int(meta.get("size_hint_bytes") or 0)
if hint >= 1_000_000_000:
    gb = hint / 1_000_000_000
    print(f"WARNING: {meta['name']} tiles may be ~{gb:.1f} GB (zoom-dependent). Ensure free disk.", flush=True)

default_zoom = int(meta.get("maxzoom") or defaults.get("maxzoom") or 12)
zoom = int(os.environ.get("ATLAS_PMTILES_MAXZOOM") or default_zoom)
print(f"Fetching {meta['name']} ({cc}) → {dest / (cc + '.pmtiles')} (maxzoom={zoom})", flush=True)
print("Source: Protomaps basemap extract (ODbL / © OpenStreetMap contributors)", flush=True)
try:
    out = fetch_country_pmtiles(
        dest,
        country=cc,
        bbox=meta["bbox"],
        maxzoom=zoom,
        direct_url=os.environ.get("ATLAS_PMTILES_URL") or None,
        atlas_root=Path(os.environ.get("ATLAS_ROOT") or "/tmp/atlas-fetch-cache"),
        progress_file=dest / ".fetch-progress",
    )
except PackError as e:
    print(f"ERROR: {e}", file=sys.stderr)
    sys.exit(1)
print(f"Wrote {out} ({out.stat().st_size} bytes)")
print("Optional rebuild to embed tiles in pack:")
print("  ./scripts/build-content-packs.sh --maps-only")
print("Or install the stub pack and let Command Centre fetch into /srv/atlas/maps/<cc>/")
PY
