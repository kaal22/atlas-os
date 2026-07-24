#!/usr/bin/env bash
# Sign an Atlas .atlas-update bundle (replaces DEV-UNSIGNED-PLACEHOLDER).
#
# Signs checksums.sha256 with openssl dgst -sha256 -sign, verifies against the
# matching .pub, then repacks. Does NOT invent or commit private keys.
#
# Usage:
#   ./scripts/sign-update-bundle.sh path/to/bundle.atlas-update [--key PATH]
#
# Key resolution (first match wins):
#   1. --key PATH
#   2. ATLAS_UPDATE_SIGNING_KEY
#   3. release/keys/dev/atlas-dev-package.key
#
# Production: set ATLAS_UPDATE_SIGNING_KEY (or --key) to the offline
# atlas-update-metadata private key path. Never commit that key.
#
# Public key for verify: same basename with .pub (KEY.key → KEY.pub).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
BUNDLE=""
KEY="${ATLAS_UPDATE_SIGNING_KEY:-}"

usage() {
  cat <<EOF
Usage: $0 BUNDLE.atlas-update [--key PATH]

Replace the bundle signature with a real openssl RSA signature of checksums.sha256,
verify with the matching .pub, and rewrite the archive in place.

Default key: release/keys/dev/atlas-dev-package.key
            (or ATLAS_UPDATE_SIGNING_KEY)

Generate a local dev keypair first:
  ./scripts/generate-dev-keys.sh
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --key)
      KEY="$2"
      shift 2
      ;;
    -*)
      echo "Unknown arg: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      if [[ -n "$BUNDLE" ]]; then
        echo "Unexpected arg: $1" >&2
        exit 1
      fi
      BUNDLE="$1"
      shift
      ;;
  esac
done

if [[ -z "$BUNDLE" ]]; then
  usage >&2
  exit 1
fi

if [[ ! -f "$BUNDLE" ]]; then
  echo "ERROR: bundle not found: $BUNDLE" >&2
  exit 1
fi

if [[ -z "$KEY" ]]; then
  KEY="$ROOT/release/keys/dev/atlas-dev-package.key"
fi

if [[ ! -f "$KEY" ]]; then
  echo "ERROR: signing key not found: $KEY" >&2
  echo "Run ./scripts/generate-dev-keys.sh for a local dev key, or pass --key / ATLAS_UPDATE_SIGNING_KEY." >&2
  exit 1
fi

# Prefer KEY.pub next to KEY; also accept KEY with .key → .pub swap.
PUB="${KEY%.key}.pub"
if [[ "$PUB" == "$KEY" ]]; then
  PUB="${KEY}.pub"
fi
if [[ ! -f "$PUB" ]]; then
  # Fall back to committed package public key (dev) for verify-only mismatch catch.
  if [[ -f "$ROOT/packages/atlas-updater/usr/share/atlas/keys/atlas-dev-package.pub" ]]; then
    PUB="$ROOT/packages/atlas-updater/usr/share/atlas/keys/atlas-dev-package.pub"
    echo "WARN: no .pub beside key; verifying with $PUB" >&2
  else
    echo "ERROR: public key not found for $KEY (expected $PUB)" >&2
    exit 1
  fi
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "ERROR: openssl is required to sign update bundles" >&2
  exit 1
fi

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/atlas-sign-update.XXXXXX")"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

STAGE="$WORKDIR/stage"
mkdir -p "$STAGE"
tar -xzf "$BUNDLE" -C "$STAGE"

CHECKSUMS="$STAGE/checksums.sha256"
SIG="$STAGE/signature"
if [[ ! -f "$CHECKSUMS" ]]; then
  echo "ERROR: checksums.sha256 missing inside bundle" >&2
  exit 1
fi
if [[ ! -f "$STAGE/update.json" ]]; then
  echo "ERROR: update.json missing inside bundle" >&2
  exit 1
fi

openssl dgst -sha256 -sign "$KEY" -out "$SIG" "$CHECKSUMS"

if ! openssl dgst -sha256 -verify "$PUB" -signature "$SIG" "$CHECKSUMS" >/dev/null; then
  echo "ERROR: signature verification failed against $PUB" >&2
  exit 1
fi

OUT_TMP="$WORKDIR/out.atlas-update"
tar -C "$STAGE" -czf "$OUT_TMP" .
# Atomic replace
mv -f "$OUT_TMP" "$BUNDLE"

DIGEST="$(sha256sum "$BUNDLE" | awk '{print $1}')"
SIZE="$(stat -c%s "$BUNDLE" 2>/dev/null || stat -f%z "$BUNDLE")"
echo "Signed $BUNDLE"
echo "  key:     $KEY"
echo "  pubkey:  $PUB"
echo "  sha256:  $DIGEST"
echo "  size:    $SIZE"
