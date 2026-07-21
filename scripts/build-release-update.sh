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
STAGING="$OUT_DIR/staging"
BUNDLE_NAME="atlas-update-${FROM_VER}-to-${TO_VER}.atlas-update"
BUNDLE_PATH="$OUT_DIR/$BUNDLE_NAME"

rm -rf "$STAGING"
mkdir -p "$STAGING/payload"

IFS=',' read -ra PKG_LIST <<< "$PACKAGES"
for pkg in "${PKG_LIST[@]}"; do
  pkg_dir="$ROOT/packages/$pkg"
  if [[ ! -d "$pkg_dir" ]]; then
    echo "WARN: package dir $pkg_dir not found, skipping"
    continue
  fi
  echo "Staging $pkg..."
  while IFS= read -r -d '' f; do
    rel="${f#"$pkg_dir"/}"
    case "$rel" in
      __pycache__/*|*/__pycache__/*|*.pyc) continue ;;
    esac
    mode="644"
    [[ "$rel" == usr/bin/* ]] && mode="755"
    install -D -m "$mode" "$f" "$STAGING/payload/$rel"
  done < <(find "$pkg_dir" -type f -print0)
done

COMPONENTS=$(printf '"%s",' "${PKG_LIST[@]}")
COMPONENTS="[${COMPONENTS%,}]"

cat > "$STAGING/update.json" <<EOF
{
  "schema": "atlas.update/v1",
  "from_version": "$FROM_VER",
  "to_version": "$TO_VER",
  "version": "$TO_VER",
  "publisher": "Atlas OS",
  "digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000",
  "components": $COMPONENTS,
  "health_urls": ["http://127.0.0.1:8787/"],
  "restart_services": ["atlas-command-centre", "atlas-system-daemon", "atlas-agent-runtime"]
}
EOF

cat > "$STAGING/RELEASE_NOTES.txt" <<EOF
Atlas OS $TO_VER (from $FROM_VER)

See https://github.com/kaal22/atlas-os/releases/tag/v$TO_VER for full changelog.
EOF

export ATLAS_ALLOW_UNSIGNED=1
export ATLAS_ROOT="$ROOT"
export ATLAS_STAGING="$STAGING"
export ATLAS_BUNDLE="$BUNDLE_PATH"
python3 - <<'PY'
import os, sys
from pathlib import Path

ROOT = Path(os.environ["ATLAS_ROOT"])
sys.path.insert(0, str(ROOT / "packages" / "atlas-updater" / "usr" / "lib" / "atlas"))
from updater import build_update_bundle

staging = Path(os.environ["ATLAS_STAGING"])
out = Path(os.environ["ATLAS_BUNDLE"])
digest = build_update_bundle(staging, out)
print(f"Built {out} ({digest})")
PY

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
