# Development keys

Private `*.key` files are gitignored. Only `*.pub` may be committed.
Production keys are managed per docs/signing/SIGNING_PLAN.md.

Ship the public key to appliances via:

  packages/atlas-updater/usr/share/atlas/keys/atlas-dev-package.pub
  → /usr/share/atlas/keys/atlas-dev-package.pub

