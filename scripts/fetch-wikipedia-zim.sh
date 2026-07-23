#!/usr/bin/env bash
# Optional: download a Kiwix ZIM for Wikipedia-style offline browsing.
# Does NOT commit the ZIM into git — drops it beside curated sources for pack rebuild,
# or into /srv/atlas when ATLAS_ZIM_DEST=runtime.
#
# Usage:
#   ./scripts/fetch-wikipedia-zim.sh              # starter en_100_nopic (~13 MB)
#   ./scripts/fetch-wikipedia-zim.sh starter
#   ./scripts/fetch-wikipedia-zim.sh mini         # full English mini (~12 GB)
#   ./scripts/fetch-wikipedia-zim.sh nopic        # full English nopic (~49 GB)
#   ./scripts/fetch-wikipedia-zim.sh maxi         # full English maxi (~115 GB)
#
# Or set ATLAS_ZIM_SIZE=mini|nopic|maxi|starter and/or ATLAS_ZIM_URL / ATLAS_ZIM_NAME.
# Locked URLs match release/sources.catalog.yaml (do not use "latest").
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SIZE="${1:-${ATLAS_ZIM_SIZE:-starter}}"

case "$SIZE" in
  starter|en_100|100|default|"")
    DEFAULT_URL="https://download.kiwix.org/zim/wikipedia/wikipedia_en_100_nopic_2026-04.zim"
    DEFAULT_NAME="wikipedia_en_100_nopic.zim"
    SIZE_HINT="~13 MB"
    RUNTIME_SLUG="wikipedia-en"
    ;;
  mini|all_mini)
    DEFAULT_URL="https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_mini_2026-06.zim"
    DEFAULT_NAME="wikipedia_en_all_mini.zim"
    SIZE_HINT="~12 GB"
    RUNTIME_SLUG="wikipedia-en-mini"
    ;;
  nopic|all_nopic|no_pictures)
    DEFAULT_URL="https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_nopic_2026-06.zim"
    DEFAULT_NAME="wikipedia_en_all_nopic.zim"
    SIZE_HINT="~49 GB"
    RUNTIME_SLUG="wikipedia-en-nopic"
    ;;
  maxi|all_maxi|full)
    DEFAULT_URL="https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_maxi_2026-02.zim"
    DEFAULT_NAME="wikipedia_en_all_maxi.zim"
    SIZE_HINT="~115 GB"
    RUNTIME_SLUG="wikipedia-en-maxi"
    ;;
  -h|--help|help)
    sed -n '2,16p' "$0"
    exit 0
    ;;
  *)
    echo "Unknown size '$SIZE'. Use: starter | mini | nopic | maxi" >&2
    exit 2
    ;;
esac

DEST_MODE="${ATLAS_ZIM_DEST:-pack}"  # pack | runtime
if [[ "$DEST_MODE" == "runtime" ]]; then
  DEST_DIR="${ATLAS_ROOT:-/srv/atlas}/knowledge/packs/${RUNTIME_SLUG}"
else
  # Pack staging: starter ZIM next to curated sources; large dumps stay in a size subdir
  # so they are never accidentally embedded into the small starter pack.
  if [[ "$RUNTIME_SLUG" == "wikipedia-en" ]]; then
    DEST_DIR="$ROOT/content/packs/knowledge/wikipedia-en-curated"
  else
    DEST_DIR="$ROOT/content/packs/knowledge/wikipedia-en-curated/${RUNTIME_SLUG}"
  fi
fi
mkdir -p "$DEST_DIR"

URL="${ATLAS_ZIM_URL:-$DEFAULT_URL}"
OUT_NAME="${ATLAS_ZIM_NAME:-$DEFAULT_NAME}"

echo "Downloading $URL → $DEST_DIR/$OUT_NAME"
echo "(size $SIZE_HINT for variant '$SIZE'; full mini/nopic/maxi need lots of free disk)"
curl -fL --progress-bar -o "$DEST_DIR/$OUT_NAME.partial" "$URL"
mv -f "$DEST_DIR/$OUT_NAME.partial" "$DEST_DIR/$OUT_NAME"
ls -lh "$DEST_DIR/$OUT_NAME"

if [[ "$DEST_MODE" == "pack" ]]; then
  if [[ "$RUNTIME_SLUG" == "wikipedia-en" ]]; then
    echo "Rebuild with: ./scripts/build-content-packs.sh --knowledge-only"
  else
    echo "Large ZIM staged under $DEST_DIR (not embedded in git packs)."
    echo "Prefer Content → Install atlas.knowledge.${RUNTIME_SLUG},"
    echo "  or: ATLAS_ZIM_DEST=runtime ./scripts/fetch-wikipedia-zim.sh $SIZE"
  fi
else
  echo "Runtime drop-in complete. Re-run knowledge.index / Content → Retry ZIM if needed."
fi
