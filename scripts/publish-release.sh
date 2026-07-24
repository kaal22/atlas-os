#!/usr/bin/env bash
# Publish an Atlas OS release to GitHub Releases.
# Usage:
#   ./scripts/publish-release.sh --from 0.1.0 --to 0.1.1 --channel stable
#   [--sign|--no-sign] [--key PATH] [--notes 'text']
# Requires: gh CLI authenticated, build-release-update.sh
#
# Default: sign with dev key when present. Production:
#   ATLAS_UPDATE_SIGNING_KEY=/secure/atlas-update-metadata.key ./scripts/publish-release.sh ...
set -euo pipefail

FROM_VER=""
TO_VER=""
CHANNEL="stable"
NOTES=""
SIGN_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from) FROM_VER="$2"; shift 2;;
    --to) TO_VER="$2"; shift 2;;
    --channel) CHANNEL="$2"; shift 2;;
    --notes) NOTES="$2"; shift 2;;
    --sign) SIGN_ARGS+=(--sign); shift;;
    --no-sign) SIGN_ARGS+=(--no-sign); shift;;
    --key) SIGN_ARGS+=(--key "$2"); shift 2;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

if [[ -z "$FROM_VER" || -z "$TO_VER" ]]; then
  echo "Usage: $0 --from X.Y.Z --to X.Y.Z [--channel stable] [--notes 'text'] [--sign|--no-sign] [--key PATH]"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT_DIR="build/release"

echo "==> Building update bundle..."
"$SCRIPT_DIR/build-release-update.sh" \
  --from "$FROM_VER" \
  --to "$TO_VER" \
  --channel "$CHANNEL" \
  --out "$OUT_DIR" \
  "${SIGN_ARGS[@]+"${SIGN_ARGS[@]}"}"

BUNDLE_NAME="atlas-update-${FROM_VER}-to-${TO_VER}.atlas-update"
BUNDLE_PATH="$OUT_DIR/$BUNDLE_NAME"
BUNDLE_SHA256=$(sha256sum "$BUNDLE_PATH" | awk '{print $1}')
BUNDLE_SIZE=$(stat -c%s "$BUNDLE_PATH" 2>/dev/null || stat -f%z "$BUNDLE_PATH")

if [[ -z "$NOTES" ]]; then
  NOTES="Atlas OS v${TO_VER} update from v${FROM_VER}."
fi

PUBLISHED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)

cat > "$OUT_DIR/channel.json" <<EOF
{
  "schema": "atlas.channel/v1",
  "channel": "$CHANNEL",
  "latest": {
    "version": "$TO_VER",
    "from_versions": ["$FROM_VER", "*"],
    "bundle_filename": "$BUNDLE_NAME",
    "bundle_sha256": "$BUNDLE_SHA256",
    "bundle_size": $BUNDLE_SIZE,
    "release_notes": "$NOTES",
    "published_at": "$PUBLISHED_AT"
  },
  "update_url_base": "https://github.com/kaal22/atlas-os/releases/latest/download/"
}
EOF

echo ""
echo "==> Publishing GitHub Release v${TO_VER}..."
gh release create "v${TO_VER}" \
  --title "Atlas OS v${TO_VER}" \
  --notes "$NOTES" \
  "$BUNDLE_PATH" \
  "$OUT_DIR/channel.json"

echo ""
echo "Release published: https://github.com/kaal22/atlas-os/releases/tag/v${TO_VER}"
echo "Devices will see this update via: Check for updates"
echo "Appliances on stable/release need a signed bundle (no ATLAS_ALLOW_UNSIGNED)."
