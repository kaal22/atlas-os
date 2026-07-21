#!/usr/bin/env bash
# Build a real .atlas-update bundle from deb packages for release publishing.
# Usage: ./scripts/build-release-update.sh --from 0.1.0 --to 0.1.1 [--packages PKG1,PKG2,...]
set -euo pipefail

FROM_VER=""
TO_VER=""
PACKAGES="atlas-command-centre,atlas-agent-runtime,atlas-knowledge,atlas-updater,atlas-system-daemon"
OUT_DIR="build/release"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from) FROM_VER="$2"; shift 2;;
    --to) TO_VER="$2"; shift 2;;
    --packages) PACKAGES="$2"; shift 2;;
    --out) OUT_DIR="$2"; shift 2;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

if [[ -z "$FROM_VER" || -z "$TO_VER" ]]; then
  echo "Usage: $0 --from X.Y.Z --to X.Y.Z [--packages pkg1,pkg2,...] [--out dir]"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"

mkdir -p "$OUT_DIR/staging/payload"

IFS=',' read -ra PKG_LIST <<< "$PACKAGES"
for pkg in "${PKG_LIST[@]}"; do
  pkg_dir="$ROOT/packages/$pkg"
  if [[ ! -d "$pkg_dir" ]]; then
    echo "WARN: package dir $pkg_dir not found, skipping"
    continue
  fi
  echo "Staging $pkg..."
  cp -a "$pkg_dir"/. "$OUT_DIR/staging/payload/"
done

HEALTH_URLS='["http://127.0.0.1:8790/health","http://127.0.0.1:11434/api/tags"]'
COMPONENTS=$(printf '"%s",' "${PKG_LIST[@]}")
COMPONENTS="[${COMPONENTS%,}]"

cat > "$OUT_DIR/staging/update.json" <<EOF
{
  "schema": "atlas.update/v1",
  "version": "$TO_VER",
  "from_version": "$FROM_VER",
  "publisher": "Atlas OS",
  "components": $COMPONENTS,
  "health_check_urls": $HEALTH_URLS,
  "restart_services": ["atlas-command-centre","atlas-system-daemon","atlas-agent-runtime"]
}
EOF

cat > "$OUT_DIR/staging/RELEASE_NOTES.txt" <<EOF
Atlas OS $TO_VER (from $FROM_VER)

See https://github.com/kaal22/atlas-os/releases/tag/v$TO_VER for full changelog.
EOF

BUNDLE_NAME="atlas-update-${FROM_VER}-to-${TO_VER}.atlas-update"
BUNDLE_PATH="$OUT_DIR/$BUNDLE_NAME"

cd "$OUT_DIR/staging"
tar czf "../$BUNDLE_NAME" .
cd "$ROOT"

BUNDLE_SHA256=$(sha256sum "$BUNDLE_PATH" | awk '{print $1}')
BUNDLE_SIZE=$(stat -c%s "$BUNDLE_PATH" 2>/dev/null || stat -f%z "$BUNDLE_PATH")

echo ""
echo "Bundle built: $BUNDLE_PATH"
echo "  SHA-256: $BUNDLE_SHA256"
echo "  Size:    $BUNDLE_SIZE bytes"
echo ""
echo "BUNDLE_PATH=$BUNDLE_PATH"
echo "BUNDLE_SHA256=$BUNDLE_SHA256"
echo "BUNDLE_SIZE=$BUNDLE_SIZE"
echo "BUNDLE_NAME=$BUNDLE_NAME"
