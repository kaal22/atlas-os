#!/usr/bin/env bash
set -euo pipefail
# Generate development signing material (never for production).
#
# Creates:
#   release/keys/dev/atlas-dev-package.key   (PRIVATE — gitignored)
#   release/keys/dev/atlas-dev-package.pub   (safe to commit / ship)
#
# Use the private key to sign .atlas-update bundles:
#   ./scripts/sign-update-bundle.sh build/release/foo.atlas-update
#   # or: ./scripts/build-release-update.sh --from … --to … --sign
#
# Production update signing uses an offline atlas-update-metadata key
# (see docs/signing/SIGNING_PLAN.md). Never invent or commit production secrets.
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/release/keys/dev"
mkdir -p "$OUT"

if [[ -f "$OUT/atlas-dev-package.key" ]]; then
  echo "Dev keys already exist in $OUT — refusing to overwrite."
  exit 0
fi

if command -v openssl >/dev/null; then
  openssl genrsa -out "$OUT/atlas-dev-package.key" 3072
  openssl rsa -in "$OUT/atlas-dev-package.key" -pubout -out "$OUT/atlas-dev-package.pub"
  chmod 600 "$OUT/atlas-dev-package.key"
  echo "Generated RSA dev keypair in $OUT"
  echo "PRIVATE KEY MUST NOT BE COMMITTED"
else
  echo "openssl not found; writing placeholder public stub"
  echo "DEV-PLACEHOLDER-PUBLIC-KEY" > "$OUT/atlas-dev-package.pub"
fi

cat > "$OUT/README.md" <<'EOF'
# Development keys

Private `*.key` files are gitignored. Only `*.pub` may be committed.
Production keys are managed per docs/signing/SIGNING_PLAN.md.

After regenerating, copy the public key into the updater package so images
install it under `/usr/share/atlas/keys/`:

  cp release/keys/dev/atlas-dev-package.pub \
     packages/atlas-updater/usr/share/atlas/keys/atlas-dev-package.pub

Sign an update bundle (dev):

  ./scripts/generate-dev-keys.sh
  ./scripts/build-release-update.sh --from 0.1.0 --to 0.1.1 --sign
  # or: ./scripts/sign-update-bundle.sh path/to/bundle.atlas-update

Production (offline key, never in git):

  ATLAS_UPDATE_SIGNING_KEY=/secure/atlas-update-metadata.key \
    ./scripts/build-release-update.sh --from … --to … --sign --key "$ATLAS_UPDATE_SIGNING_KEY"
EOF
