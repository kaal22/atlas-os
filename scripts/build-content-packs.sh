#!/usr/bin/env bash
# Build Atlas content packs: country maps, kids home-learning, Wikipedia + Library ZIM SKUs.
# Usage:
#   ./scripts/build-content-packs.sh              # default ISO set + knowledge packs
#   ./scripts/build-content-packs.sh --all-maps   # every country in countries.json
#   ./scripts/build-content-packs.sh --maps-only
#   ./scripts/build-content-packs.sh --knowledge-only
# Knowledge packs: wikipedia-en (+ mini/nopic/maxi) + medicine / howto / gutenberg stubs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist/packs"
ISO_PACKS="$ROOT/config/includes.chroot/usr/share/atlas/packs"
PKG_PACKS="$ROOT/packages/atlas-content-manager/usr/share/atlas/packs"
CAT_SRC="$ROOT/content/catalogues/catalogue.json"
CAT_PKG="$ROOT/packages/atlas-content-manager/usr/share/atlas/catalogue.json"
CAT_ISO="$ROOT/config/includes.chroot/usr/share/atlas/catalogue.json"
COUNTRIES_JSON="$ROOT/content/packs/maps/countries.json"
CM_PY="$ROOT/packages/atlas-content-manager/usr/lib/atlas"

ALL_MAPS=0
MAPS_ONLY=0
KNOWLEDGE_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --all-maps) ALL_MAPS=1 ;;
    --maps-only) MAPS_ONLY=1 ;;
    --knowledge-only) KNOWLEDGE_ONLY=1 ;;
    -h|--help)
      sed -n '2,8p' "$0"
      exit 0
      ;;
  esac
done

mkdir -p "$OUT" "$ISO_PACKS" "$PKG_PACKS"
export ATLAS_ALLOW_UNSIGNED=1
export PYTHONPATH="$CM_PY${PYTHONPATH:+:$PYTHONPATH}"

build_one() {
  local stage="$1" out_pack="$2"
  python3 - <<PY
import json, os, sys
from pathlib import Path
sys.path.insert(0, r"$CM_PY")
from content_manager import build_pack
stage = Path(r"$stage")
out = Path(r"$out_pack")
os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
# First pass: write checksums + digest into manifest, then rebuild
digest = build_pack(stage, out)
m = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
m["digest"] = digest
# Approximate size from staged payload
size = sum(f.stat().st_size for f in stage.rglob("*") if f.is_file())
m["size_bytes"] = max(int(m.get("size_bytes") or 0), size)
(stage / "manifest.json").write_text(json.dumps(m, indent=2) + "\n", encoding="utf-8")
digest = build_pack(stage, out)
print("Wrote", out, digest)
PY
  cp -f "$out_pack" "$ISO_PACKS/"
  cp -f "$out_pack" "$PKG_PACKS/"
}

stage_map_country() {
  local code="$1" name="$2" bbox="$3" center="$4" size_hint="$5" size_class="$6"
  local stage tiles_src status="stub"
  stage="$(mktemp -d "${TMPDIR:-/tmp}/atlas-map-${code}.XXXXXX")"
  mkdir -p "$stage/payload" "$stage/licences" "$stage/attribution"
  tiles_src="$ROOT/content/packs/maps/${code}"
  shopt -s nullglob
  for tile in "$tiles_src"/*.pmtiles "$tiles_src"/*.mbtiles; do
    cp -a "$tile" "$stage/payload/"
    status="ready"
  done
  shopt -u nullglob
  cat > "$stage/manifest.json" <<EOF
{
  "schema": "atlas.pack/v1",
  "id": "atlas.maps.${code}",
  "version": "2026.07",
  "type": "atlas.content.map",
  "name": "${name} Offline Maps",
  "description": "Offline map pack for ${name}. Install downloads Protomaps/OSM PMTiles online when needed (ODbL); afterwards tiles work offline.",
  "size_bytes": 2048,
  "minimum_os_version": "0.1.0",
  "architectures": ["all"],
  "mount_target": "/srv/atlas/maps/${code}",
  "licences": ["ODbL-1.0"],
  "sources": ["openstreetmap", "protomaps"],
  "dependencies": [],
  "conflicts": [],
  "post_install_workflow": "maps.reindex",
  "meta": {
    "country": "${code}",
    "bbox": ${bbox},
    "center": ${center},
    "format": "pmtiles",
    "size_hint_bytes": ${size_hint},
    "size_class": "${size_class}",
    "tiles_fetch": {
      "enabled": true,
      "mode": "protomaps_extract",
      "source": "protomaps",
      "maxzoom": 11,
      "size_hint_bytes": ${size_hint},
      "licence": "ODbL-1.0",
      "attribution": "© OpenStreetMap contributors (Protomaps basemap)"
    }
  },
  "digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000"
}
EOF
  cat > "$stage/payload/README.txt" <<EOF
Atlas offline maps — ${name} (${code})

On Install (Command Centre / content manager), Atlas downloads a country PMTiles
extract from the Protomaps daily basemap (HTTP range requests) into:
  /srv/atlas/maps/${code}/${code}.pmtiles
Default max zoom is 11 (override with ATLAS_PMTILES_MAXZOOM). Large countries
may be multi-GB — check free disk first.

Licence: ODbL-1.0 — © OpenStreetMap contributors (Protomaps basemap produced work).
After download, tiles are fully offline.

Operator alternatives:
  ./scripts/fetch-country-pmtiles.sh ${code}
  ATLAS_PMTILES_URL='https://…/${code}.pmtiles' ./scripts/fetch-country-pmtiles.sh ${code}
Then rebuild with ./scripts/build-content-packs.sh --maps-only to embed tiles.
EOF
  cat > "$stage/payload/meta.json" <<EOF
{"country":"${code}","name":"${name}","bbox":${bbox},"center":${center},"format":"pmtiles","status":"${status}","size_hint_bytes":${size_hint},"tiles_source":"protomaps"}
EOF
  echo "Open Database Licence (ODbL) — © OpenStreetMap contributors. Protomaps basemap is an ODbL Produced Work; attribution required." > "$stage/licences/ODbL.txt"
  echo "© OpenStreetMap contributors — https://www.openstreetmap.org/copyright" > "$stage/attribution/OSM.txt"
  echo "Basemap extracts via Protomaps (https://protomaps.com / docs.protomaps.com/basemaps/downloads)." > "$stage/attribution/PROTOMAPS.txt"
  build_one "$stage" "$OUT/atlas-maps-${code}.atlas-pack"
  rm -rf "$stage"
}

if [[ "$KNOWLEDGE_ONLY" -eq 0 ]]; then
  echo "=== Building country map packs ==="
  while IFS=$'\t' read -r code name bbox center size_hint size_class; do
    [[ -z "$code" ]] && continue
    stage_map_country "$code" "$name" "$bbox" "$center" "$size_hint" "$size_class"
  done < <(python3 - <<PY
import json
from pathlib import Path
data = json.loads(Path(r"$COUNTRIES_JSON").read_text(encoding="utf-8"))
want = set(data.get("default_iso_set") or [])
if int("$ALL_MAPS"):
    want = {c["code"] for c in data["countries"]}
for c in data["countries"]:
    if c["code"] not in want:
        continue
    print("\t".join([
        c["code"],
        c["name"],
        json.dumps(c["bbox"]),
        json.dumps(c["center"]),
        str(int(c.get("size_hint_bytes") or 0)),
        str(c.get("size_class") or "medium"),
    ]))
PY
)
fi

if [[ "$MAPS_ONLY" -eq 0 ]]; then
  echo "=== Building kids home-learning pack ==="
  STAGE="$(mktemp -d "${TMPDIR:-/tmp}/atlas-kids.XXXXXX")"
  mkdir -p "$STAGE/payload" "$STAGE/licences" "$STAGE/attribution"
  cp -a "$ROOT/content/packs/education/kids-home-learning/." "$STAGE/payload/"
  cat > "$STAGE/manifest.json" <<'EOF'
{
  "schema": "atlas.pack/v1",
  "id": "atlas.education.kids-home",
  "version": "2026.07",
  "type": "atlas.content.education",
  "name": "Kids Home Learning",
  "description": "Offline home-learning curriculum (maths, reading, science, geography, daily routine) ingested into the agent knowledge base. Optional expand bundle via ATLAS_KIDS_EXPAND_URL.",
  "size_bytes": 32768,
  "minimum_os_version": "0.1.0",
  "architectures": ["all"],
  "mount_target": "/srv/atlas/knowledge/packs/kids-home-learning",
  "licences": ["CC-BY-4.0"],
  "sources": ["atlas-curated"],
  "dependencies": [],
  "conflicts": [],
  "post_install_workflow": "knowledge.index",
  "meta": {
    "audience": "kids",
    "language": "eng",
    "expand_fetch": {
      "enabled": true,
      "mode": "curriculum_bundle",
      "size_hint_bytes": 0,
      "licence": "CC-BY-4.0",
      "attribution": "Atlas curated education expand bundle",
      "note": "Set ATLAS_KIDS_EXPAND_URL or meta.expand_fetch.url to a .tar.gz/.zip of extra Markdown lessons. Starter curriculum ships offline without network."
    }
  },
  "digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000"
}
EOF
  echo "Creative Commons Attribution 4.0 — Atlas curated home-learning lessons." > "$STAGE/licences/CC-BY-4.0.txt"
  echo "Atlas OS curated education content (original short lessons)." > "$STAGE/attribution/ATLAS.txt"
  build_one "$STAGE" "$OUT/atlas-education-kids-home.atlas-pack"
  rm -rf "$STAGE"

  echo "=== Building Wikipedia English knowledge packs ==="
  # Shared licence/attribution snippets for all Wikipedia SKUs.
  write_wiki_legal() {
    local stage="$1"
    echo "CC BY-SA 4.0 — Wikipedia adapted text. Share-alike applies to derivatives." > "$stage/licences/CC-BY-SA-4.0.txt"
    echo "GFDL may also apply to some Wikipedia materials." > "$stage/licences/GFDL.txt"
    echo "© Wikipedia contributors — https://wikipedia.org" > "$stage/attribution/WIKIPEDIA.txt"
    echo "Kiwix ZIM archives — https://kiwix.org / https://download.kiwix.org" > "$stage/attribution/KIWIX.txt"
  }

  # Starter: curated Markdown RAG + small en_100_nopic ZIM (~13 MB).
  STAGE="$(mktemp -d "${TMPDIR:-/tmp}/atlas-wiki.XXXXXX")"
  mkdir -p "$STAGE/payload/articles" "$STAGE/licences" "$STAGE/attribution"
  cp -a "$ROOT/content/packs/knowledge/wikipedia-en-curated/README.md" "$STAGE/payload/"
  cp -a "$ROOT/content/packs/knowledge/wikipedia-en-curated/articles/." "$STAGE/payload/articles/"
  shopt -s nullglob
  for zim in "$ROOT/content/packs/knowledge/wikipedia-en-curated/"*.zim; do
    cp -a "$zim" "$STAGE/payload/"
  done
  shopt -u nullglob
  cat > "$STAGE/manifest.json" <<'EOF'
{
  "schema": "atlas.pack/v1",
  "id": "atlas.knowledge.wikipedia-en",
  "version": "2026.07",
  "type": "atlas.content.knowledge",
  "name": "Wikipedia EN starter (curated + top-100)",
  "description": "Curated Wikipedia-style articles for agent RAG, plus install-time download of English top-100 nopic ZIM (~13 MB) for Kiwix. For full English dumps use mini / nopic / maxi catalogue packs.",
  "size_bytes": 32768,
  "minimum_os_version": "0.1.0",
  "architectures": ["all"],
  "mount_target": "/srv/atlas/knowledge/packs/wikipedia-en",
  "licences": ["CC-BY-SA-4.0", "GFDL"],
  "sources": ["wikipedia", "kiwix"],
  "dependencies": [],
  "conflicts": [],
  "post_install_workflow": "knowledge.index",
  "meta": {
    "language": "eng",
    "kind": "wikipedia",
    "variant": "starter",
    "size_hint_bytes": 14000000,
    "size_class": "small",
    "zim_fetch": {
      "enabled": true,
      "mode": "kiwix_download",
      "default_url": "https://download.kiwix.org/zim/wikipedia/wikipedia_en_100_nopic_2026-04.zim",
      "filename": "wikipedia_en_100_nopic.zim",
      "size_hint_bytes": 14000000,
      "licence": "CC-BY-SA-4.0",
      "attribution": "© Wikipedia contributors — offline ZIM via Kiwix"
    }
  },
  "digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000"
}
EOF
  write_wiki_legal "$STAGE"
  build_one "$STAGE" "$OUT/atlas-knowledge-wikipedia-en.atlas-pack"
  rm -rf "$STAGE"

  # Large ZIM SKUs: minimal stub packs that trigger zim_fetch (no multi-GB ZIMs in git).
  # Locked filenames from release/sources.catalog.yaml (do not use "latest").
  build_wiki_zim_sku() {
    local pack_id="$1" variant="$2" name="$3" desc="$4" size_hint="$5" zim_url="$6" zim_file="$7" out_name="$8"
    local stage gb
    stage="$(mktemp -d "${TMPDIR:-/tmp}/atlas-wiki-${variant}.XXXXXX")"
    mkdir -p "$stage/payload" "$stage/licences" "$stage/attribution"
    gb="$(python3 -c "print(f'{int(${size_hint})/1e9:.0f}')")"
    cat > "$stage/payload/README.md" <<EOF
# ${name}

Stub pack: curated Markdown is in **Wikipedia EN starter**. This SKU downloads the
Kiwix English Wikipedia **${variant}** ZIM on install (~${gb} GB) and registers it with Kiwix Serve.

Do not commit the ZIM into git. Skip fetch with \`ATLAS_ZIM_SKIP_FETCH=1\`.
Override URL with \`ATLAS_ZIM_URL\` / \`ATLAS_ZIM_NAME\`.

Default URL: ${zim_url}
EOF
    PACK_ID="$pack_id" VARIANT="$variant" NAME="$name" DESC="$desc" \
    SIZE_HINT="$size_hint" ZIM_URL="$zim_url" ZIM_FILE="$zim_file" STAGE="$stage" \
    python3 - <<'PY'
import json, os
from pathlib import Path
variant = os.environ["VARIANT"]
others = {
    "mini": ["atlas.knowledge.wikipedia-en-nopic", "atlas.knowledge.wikipedia-en-maxi"],
    "nopic": ["atlas.knowledge.wikipedia-en-mini", "atlas.knowledge.wikipedia-en-maxi"],
    "maxi": ["atlas.knowledge.wikipedia-en-mini", "atlas.knowledge.wikipedia-en-nopic"],
}
size_hint = int(os.environ["SIZE_HINT"])
manifest = {
    "schema": "atlas.pack/v1",
    "id": os.environ["PACK_ID"],
    "version": "2026.07",
    "type": "atlas.content.knowledge",
    "name": os.environ["NAME"],
    "description": os.environ["DESC"],
    "size_bytes": 4096,
    "minimum_os_version": "0.1.0",
    "architectures": ["all"],
    "mount_target": f"/srv/atlas/knowledge/packs/wikipedia-en-{variant}",
    "licences": ["CC-BY-SA-4.0", "GFDL"],
    "sources": ["wikipedia", "kiwix"],
    "dependencies": [],
    "conflicts": others.get(variant, []),
    "post_install_workflow": "knowledge.index",
    "meta": {
        "language": "eng",
        "kind": "wikipedia",
        "variant": variant,
        "size_hint_bytes": size_hint,
        "size_class": "large",
        "zim_fetch": {
            "enabled": True,
            "mode": "kiwix_download",
            "default_url": os.environ["ZIM_URL"],
            "filename": os.environ["ZIM_FILE"],
            "size_hint_bytes": size_hint,
            "licence": "CC-BY-SA-4.0",
            "attribution": "© Wikipedia contributors — offline ZIM via Kiwix",
        },
    },
    "digest": "sha256:" + ("0" * 64),
}
Path(os.environ["STAGE"], "manifest.json").write_text(
    json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
)
PY
    write_wiki_legal "$stage"
    build_one "$stage" "$OUT/${out_name}"
    rm -rf "$stage"
  }

  build_wiki_zim_sku \
    "atlas.knowledge.wikipedia-en-mini" "mini" \
    "Wikipedia EN mini" \
    "Full English Wikipedia mini ZIM (~12 GB) for Kiwix. Large download — confirm free disk before install." \
    "12000000000" \
    "https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_mini_2026-06.zim" \
    "wikipedia_en_all_mini.zim" \
    "atlas-knowledge-wikipedia-en-mini.atlas-pack"

  build_wiki_zim_sku \
    "atlas.knowledge.wikipedia-en-nopic" "nopic" \
    "Wikipedia EN nopic" \
    "Full English Wikipedia without pictures (~49 GB) for Kiwix. Large download — confirm free disk before install." \
    "49000000000" \
    "https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_nopic_2026-06.zim" \
    "wikipedia_en_all_nopic.zim" \
    "atlas-knowledge-wikipedia-en-nopic.atlas-pack"

  build_wiki_zim_sku \
    "atlas.knowledge.wikipedia-en-maxi" "maxi" \
    "Wikipedia EN maxi" \
    "Full English Wikipedia with media (~115 GB) for Kiwix. Very large download — confirm free disk / external storage before install." \
    "115000000000" \
    "https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_maxi_2026-02.zim" \
    "wikipedia_en_all_maxi.zim" \
    "atlas-knowledge-wikipedia-en-maxi.atlas-pack"

  # Library ZIM SKUs (medical / how-to / Gutenberg) — stub packs + zim_fetch only.
  build_library_zim_sku() {
    local pack_id="$1" slug="$2" name="$3" desc="$4" size_hint="$5" size_class="$6" \
      zim_url="$7" zim_file="$8" out_name="$9" licence_note="${10}" size_warning="${11:-}"
    local stage
    stage="$(mktemp -d "${TMPDIR:-/tmp}/atlas-lib-${slug}.XXXXXX")"
    mkdir -p "$stage/payload" "$stage/licences" "$stage/attribution"
    cat > "$stage/payload/README.md" <<EOF
# ${name}

Stub pack: downloads the Kiwix ZIM on install and registers it with Atlas Library
(Kiwix Serve). Do not commit the ZIM into git.

Default URL: ${zim_url}
Skip fetch with \`ATLAS_ZIM_SKIP_FETCH=1\`.
EOF
    PACK_ID="$pack_id" SLUG="$slug" NAME="$name" DESC="$desc" \
    SIZE_HINT="$size_hint" SIZE_CLASS="$size_class" ZIM_URL="$zim_url" ZIM_FILE="$zim_file" \
    LICENCE_NOTE="$licence_note" SIZE_WARNING="$size_warning" STAGE="$stage" \
    python3 - <<'PY'
import json, os
from pathlib import Path
size_hint = int(os.environ["SIZE_HINT"])
size_class = os.environ["SIZE_CLASS"]
slug = os.environ["SLUG"]
manifest = {
    "schema": "atlas.pack/v1",
    "id": os.environ["PACK_ID"],
    "version": "2026.07",
    "type": "atlas.content.knowledge",
    "name": os.environ["NAME"],
    "description": os.environ["DESC"],
    "size_bytes": 4096,
    "minimum_os_version": "0.1.0",
    "architectures": ["all"],
    "mount_target": f"/srv/atlas/knowledge/packs/{slug}",
    "licences": ["CC-BY-SA-4.0"],
    "sources": ["kiwix"],
    "dependencies": [],
    "conflicts": [],
    "post_install_workflow": "knowledge.index",
    "meta": {
        "language": "eng",
        "kind": "library_zim",
        "variant": slug,
        "size_hint_bytes": size_hint,
        "size_class": size_class,
        "zim_fetch": {
            "enabled": True,
            "mode": "kiwix_download",
            "default_url": os.environ["ZIM_URL"],
            "filename": os.environ["ZIM_FILE"],
            "size_hint_bytes": size_hint,
            "licence": "CC-BY-SA-4.0",
            "attribution": os.environ.get("LICENCE_NOTE") or "Offline ZIM via Kiwix",
        },
    },
    "digest": "sha256:" + ("0" * 64),
}
warn = (os.environ.get("SIZE_WARNING") or "").strip()
if warn:
    manifest["meta"]["size_warning"] = warn
Path(os.environ["STAGE"], "manifest.json").write_text(
    json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
)
PY
    echo "${licence_note}" > "$stage/licences/LICENCE.txt"
    echo "Kiwix ZIM archives — https://kiwix.org / https://download.kiwix.org" > "$stage/attribution/KIWIX.txt"
    build_one "$stage" "$OUT/${out_name}"
    rm -rf "$stage"
  }

  build_library_zim_sku \
    "atlas.knowledge.medicine-en" "medicine-en" \
    "Medical / first aid (EN)" \
    "English Wikipedia medicine mini ZIM (~155 MB) for Atlas Library (Kiwix). Offline medical and first-aid reference." \
    "155000000" "medium" \
    "https://download.kiwix.org/zim/wikipedia/wikipedia_en_medicine_mini_2026-04.zim" \
    "wikipedia_en_medicine_mini.zim" \
    "atlas-knowledge-medicine-en.atlas-pack" \
    "CC BY-SA 4.0 / GFDL — © Wikipedia contributors (medicine ZIM via Kiwix)"

  build_library_zim_sku \
    "atlas.knowledge.howto-ifixit-en" "howto-ifixit-en" \
    "DIY repair / how-to (iFixit EN)" \
    "iFixit English repair guides ZIM (~3.3 GB) for Atlas Library. Large download — confirm free disk before install." \
    "3300000000" "large" \
    "https://download.kiwix.org/zim/ifixit/ifixit_en_all_2025-12.zim" \
    "ifixit_en_all.zim" \
    "atlas-knowledge-howto-ifixit-en.atlas-pack" \
    "iFixit content via Kiwix ZIM — see iFixit licensing" \
    "iFixit English is ~3.3 GB. Ensure free disk before installing."

  build_library_zim_sku \
    "atlas.knowledge.gutenberg-en" "gutenberg-en" \
    "Project Gutenberg books (EN literature)" \
    "Project Gutenberg English literature slice (LCC PN, ~3 GB) for Atlas Library. Full English Gutenberg (~206 GB) is OEM/external only." \
    "3000000000" "large" \
    "https://download.kiwix.org/zim/gutenberg/gutenberg_en_lcc-pn_2026-03.zim" \
    "gutenberg_en_lcc-pn.zim" \
    "atlas-knowledge-gutenberg-en.atlas-pack" \
    "Public domain / Project Gutenberg — offline ZIM via Kiwix" \
    "Gutenberg literature slice is ~3 GB. Full English collection is ~206 GB (not a default SKU)."
fi

echo "=== Writing catalogue.json ==="
python3 - <<PY
import json
from pathlib import Path
root = Path(r"$ROOT")
out = Path(r"$OUT")
countries = json.loads((root / "content/packs/maps/countries.json").read_text(encoding="utf-8"))
defaults = countries.get("tiles_defaults") or {}
built_maps = {p.stem.replace("atlas-maps-", "") for p in out.glob("atlas-maps-*.atlas-pack")}
packs = []
for c in countries["countries"]:
    code = c["code"]
    bundle = f"atlas-maps-{code}.atlas-pack"
    hint = int(c.get("size_hint_bytes") or 0)
    size_class = c.get("size_class") or "medium"
    entry = {
        "id": f"atlas.maps.{code}",
        "version": "2026.07",
        "type": "atlas.content.map",
        "name": f"{c['name']} Offline Maps",
        "description": (
            f"Offline maps for {c['name']}. Install pulls a Protomaps/OSM PMTiles extract "
            f"online (max zoom {defaults.get('maxzoom', 11)}), then works offline. "
            f"Licence: ODbL — © OpenStreetMap contributors."
        ),
        "size_hint_bytes": hint or 2048,
        "size_class": size_class,
        "signed": False,
        "channel": "alpha",
        "country": code,
        "category": "maps",
        "download_on_install": True,
        "tiles_source": defaults.get("source") or "protomaps",
        "tiles_fetch": {
            "mode": defaults.get("mode") or "protomaps_extract",
            "maxzoom": defaults.get("maxzoom") or 11,
            "size_hint_bytes": hint,
        },
        "licence_note": defaults.get("attribution")
        or "© OpenStreetMap contributors (Protomaps basemap, ODbL-1.0)",
    }
    if size_class == "large":
        entry["size_warning"] = (
            f"{c['name']} tiles may be multi-GB at zoom {defaults.get('maxzoom', 11)}. "
            "Ensure free disk before installing."
        )
    pkg_pack = root / "packages/atlas-content-manager/usr/share/atlas/packs" / bundle
    if code in built_maps or pkg_pack.is_file():
        entry["bundle_file"] = bundle
    packs.append(entry)

packs.append({
    "id": "atlas.models.starter",
    "version": "0.1.0",
    "type": "atlas.content.model",
    "name": "Starter Models (qwen3:4b + nomic-embed-text)",
    "description": "Offline import of chat and embedding models.",
    "size_hint_bytes": 0,
    "signed": False,
    "channel": "alpha",
    "bundle_file": "atlas-models-starter.atlas-pack",
    "category": "models",
})

kids_bundle = "atlas-education-kids-home.atlas-pack"
packs.append({
    "id": "atlas.education.kids-home",
    "version": "2026.07",
    "type": "atlas.content.education",
    "name": "Kids Home Learning",
    "description": (
        "Starter home-learning curriculum (maths, reading, science, geography, routine) "
        "indexed for local AI tutors. Works offline on install; optional expand via ATLAS_KIDS_EXPAND_URL."
    ),
    "size_hint_bytes": (out / kids_bundle).stat().st_size if (out / kids_bundle).is_file() else 32768,
    "size_class": "small",
    "signed": False,
    "channel": "alpha",
    "bundle_file": kids_bundle,
    "category": "education",
    "licence_note": "CC BY 4.0 — Atlas curated lessons",
    "expand_fetch": {
        "mode": "curriculum_bundle",
        "note": "Set ATLAS_KIDS_EXPAND_URL for optional larger curriculum download",
    },
})

# Wikipedia catalogue SKUs (locked ZIM URLs from release/sources.catalog.yaml).
wiki_skus = [
    {
        "id": "atlas.knowledge.wikipedia-en",
        "name": "Wikipedia EN starter (curated + top-100)",
        "description": (
            "Curated Wikipedia articles for agent RAG, plus install-time download of English "
            "top-100 nopic ZIM (~13 MB) for Kiwix. For full dumps install mini / nopic / maxi."
        ),
        "size_hint_bytes": 14_000_000,
        "size_class": "small",
        "bundle_file": "atlas-knowledge-wikipedia-en.atlas-pack",
        "zim_fetch": {
            "mode": "kiwix_download",
            "default_url": "https://download.kiwix.org/zim/wikipedia/wikipedia_en_100_nopic_2026-04.zim",
            "filename": "wikipedia_en_100_nopic.zim",
            "size_hint_bytes": 14_000_000,
        },
    },
    {
        "id": "atlas.knowledge.wikipedia-en-mini",
        "name": "Wikipedia EN mini",
        "description": (
            "Full English Wikipedia mini ZIM (~12 GB) for Kiwix. Large download — "
            "confirm free disk before install."
        ),
        "size_hint_bytes": 12_000_000_000,
        "size_class": "large",
        "size_warning": (
            "English Wikipedia mini is ~12 GB. Ensure free disk before installing."
        ),
        "bundle_file": "atlas-knowledge-wikipedia-en-mini.atlas-pack",
        "zim_fetch": {
            "mode": "kiwix_download",
            "default_url": "https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_mini_2026-06.zim",
            "filename": "wikipedia_en_all_mini.zim",
            "size_hint_bytes": 12_000_000_000,
        },
    },
    {
        "id": "atlas.knowledge.wikipedia-en-nopic",
        "name": "Wikipedia EN nopic",
        "description": (
            "Full English Wikipedia without pictures (~49 GB) for Kiwix. Large download — "
            "confirm free disk before install."
        ),
        "size_hint_bytes": 49_000_000_000,
        "size_class": "large",
        "size_warning": (
            "English Wikipedia nopic is ~49 GB. Ensure free disk before installing."
        ),
        "bundle_file": "atlas-knowledge-wikipedia-en-nopic.atlas-pack",
        "zim_fetch": {
            "mode": "kiwix_download",
            "default_url": "https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_nopic_2026-06.zim",
            "filename": "wikipedia_en_all_nopic.zim",
            "size_hint_bytes": 49_000_000_000,
        },
    },
    {
        "id": "atlas.knowledge.wikipedia-en-maxi",
        "name": "Wikipedia EN maxi",
        "description": (
            "Full English Wikipedia with media (~115 GB) for Kiwix. Very large download — "
            "confirm free disk / external storage before install."
        ),
        "size_hint_bytes": 115_000_000_000,
        "size_class": "large",
        "size_warning": (
            "English Wikipedia maxi is ~115 GB. Prefer external SSD / OEM preload; "
            "ensure free disk before installing."
        ),
        "bundle_file": "atlas-knowledge-wikipedia-en-maxi.atlas-pack",
        "zim_fetch": {
            "mode": "kiwix_download",
            "default_url": "https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_maxi_2026-02.zim",
            "filename": "wikipedia_en_all_maxi.zim",
            "size_hint_bytes": 115_000_000_000,
        },
    },
    {
        "id": "atlas.knowledge.medicine-en",
        "name": "Medical / first aid (EN)",
        "description": (
            "English Wikipedia medicine mini ZIM (~155 MB) for Atlas Library (Kiwix). "
            "Offline medical and first-aid reference."
        ),
        "size_hint_bytes": 155_000_000,
        "size_class": "medium",
        "bundle_file": "atlas-knowledge-medicine-en.atlas-pack",
        "licence_note": "CC BY-SA 4.0 / GFDL — © Wikipedia contributors (medicine ZIM via Kiwix)",
        "zim_fetch": {
            "mode": "kiwix_download",
            "default_url": "https://download.kiwix.org/zim/wikipedia/wikipedia_en_medicine_mini_2026-04.zim",
            "filename": "wikipedia_en_medicine_mini.zim",
            "size_hint_bytes": 155_000_000,
        },
    },
    {
        "id": "atlas.knowledge.howto-ifixit-en",
        "name": "DIY repair / how-to (iFixit EN)",
        "description": (
            "iFixit English repair guides ZIM (~3.3 GB) for Atlas Library. "
            "Large download — confirm free disk before install."
        ),
        "size_hint_bytes": 3_300_000_000,
        "size_class": "large",
        "size_warning": "iFixit English is ~3.3 GB. Ensure free disk before installing.",
        "bundle_file": "atlas-knowledge-howto-ifixit-en.atlas-pack",
        "licence_note": "iFixit content via Kiwix ZIM — see iFixit licensing",
        "zim_fetch": {
            "mode": "kiwix_download",
            "default_url": "https://download.kiwix.org/zim/ifixit/ifixit_en_all_2025-12.zim",
            "filename": "ifixit_en_all.zim",
            "size_hint_bytes": 3_300_000_000,
        },
    },
    {
        "id": "atlas.knowledge.gutenberg-en",
        "name": "Project Gutenberg books (EN literature)",
        "description": (
            "Project Gutenberg English literature slice (LCC PN, ~3 GB) for Atlas Library. "
            "Full English Gutenberg (~206 GB) is OEM/external only."
        ),
        "size_hint_bytes": 3_000_000_000,
        "size_class": "large",
        "size_warning": (
            "Gutenberg literature slice is ~3 GB. Full English collection is ~206 GB "
            "(not a default SKU)."
        ),
        "bundle_file": "atlas-knowledge-gutenberg-en.atlas-pack",
        "licence_note": "Public domain / Project Gutenberg — offline ZIM via Kiwix",
        "zim_fetch": {
            "mode": "kiwix_download",
            "default_url": "https://download.kiwix.org/zim/gutenberg/gutenberg_en_lcc-pn_2026-03.zim",
            "filename": "gutenberg_en_lcc-pn.zim",
            "size_hint_bytes": 3_000_000_000,
        },
    },
]
for w in wiki_skus:
    entry = {
        "id": w["id"],
        "version": "2026.07",
        "type": "atlas.content.knowledge",
        "name": w["name"],
        "description": w["description"],
        "size_hint_bytes": w["size_hint_bytes"],
        "size_class": w["size_class"],
        "signed": False,
        "channel": "alpha",
        "bundle_file": w["bundle_file"],
        "category": "knowledge",
        "language": "en",
        "download_on_install": True,
        "zim_fetch": w["zim_fetch"],
        "licence_note": w.get("licence_note")
        or "CC BY-SA 4.0 / GFDL — © Wikipedia contributors (Kiwix ZIM)",
    }
    if w.get("size_warning"):
        entry["size_warning"] = w["size_warning"]
    packs.append(entry)

catalogue = {"schema": "atlas.pack/v1", "catalogue_version": "0.2.3", "packs": packs}
for dest in [
    root / "content/catalogues/catalogue.json",
    root / "packages/atlas-content-manager/usr/share/atlas/catalogue.json",
    root / "config/includes.chroot/usr/share/atlas/catalogue.json",
]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        dest.write_text(json.dumps(catalogue, indent=2) + "\n", encoding="utf-8")
        print("Wrote", dest)
    except PermissionError:
        print("WARN: cannot write", dest, "(permission denied — copy as root later)")
print(f"{len(packs)} catalogue entries")
PY

# Compatibility: keep UK stub filename used by older scripts
if [[ -f "$OUT/atlas-maps-uk.atlas-pack" ]]; then
  cp -f "$OUT/atlas-maps-uk.atlas-pack" "$OUT/atlas-maps-uk-stub.atlas-pack"
  cp -f "$OUT/atlas-maps-uk.atlas-pack" "$ISO_PACKS/atlas-maps-uk-stub.atlas-pack"
  cp -f "$OUT/atlas-maps-uk.atlas-pack" "$PKG_PACKS/atlas-maps-uk-stub.atlas-pack"
fi

# Keep dev-sync.manifest map-pack lines aligned with staged atlas-maps-*.atlas-pack files.
echo "=== Syncing map packs into dev-sync.manifest ==="
python3 - <<PY
from pathlib import Path
root = Path(r"$ROOT")
manifest = root / "scripts/dev-sync.manifest"
pkg = root / "packages/atlas-content-manager/usr/share/atlas/packs"
packs = sorted(
    p.name for p in pkg.glob("atlas-maps-*.atlas-pack")
    if not p.name.endswith("-stub.atlas-pack")
)
lines = manifest.read_text(encoding="utf-8").splitlines(keepends=True)
out = []
i = 0
while i < len(lines):
    line = lines[i]
    stripped = line.strip()
    # Drop old map-pack entries (and the section comment) so we can rewrite them.
    if stripped.startswith("# Map stub packs") or (
        stripped.startswith("packages/atlas-content-manager/usr/share/atlas/packs/atlas-maps-")
        and "|/usr/share/atlas/packs/atlas-maps-" in stripped
    ):
        i += 1
        continue
    # Insert refreshed block just before the first non-map packs line after knowledge packs,
    # or immediately after wikipedia-en-maxi if present.
    out.append(line)
    if stripped.startswith(
        "packages/atlas-content-manager/usr/share/atlas/packs/atlas-knowledge-gutenberg-en.atlas-pack|"
    ):
        out.append(
            "# Map stub packs (all catalogue countries). Regenerated by build-content-packs.sh.\n"
        )
        for name in packs:
            out.append(
                f"packages/atlas-content-manager/usr/share/atlas/packs/{name}"
                f"|/usr/share/atlas/packs/{name}|\n"
            )
    i += 1
manifest.write_text("".join(out), encoding="utf-8")
print(f"Wrote {len(packs)} map pack paths into {manifest}")
PY

echo "Done. Packs in $OUT"
ls -la "$OUT"/*.atlas-pack 2>/dev/null || true
