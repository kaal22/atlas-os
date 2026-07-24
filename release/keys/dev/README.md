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
