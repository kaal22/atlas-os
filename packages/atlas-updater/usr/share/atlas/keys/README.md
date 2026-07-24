# Atlas update public keys

Installed systems verify `.atlas-update` signatures against public keys in this
directory (`/usr/share/atlas/keys/` on the device).

| File | Role |
|------|------|
| `atlas-update-metadata.pub` | Production update-manifest key (release ceremony) |
| `atlas-release-package.pub` | Optional alias / APT release key when shared |
| `atlas-dev-package.pub` | Development key from `scripts/generate-dev-keys.sh` |

**Never** place private keys here. Production private material stays offline per
`docs/signing/SIGNING_PLAN.md`.

Until a release ceremony publishes `atlas-update-metadata.pub`, only the committed
dev public key is shipped. Stable/release channels still refuse
`DEV-UNSIGNED-PLACEHOLDER` unless `ATLAS_ALLOW_UNSIGNED=1` (alpha/dev only).
