# Signing Key Plan

Status: Phase 0 foundation  
Date: 2026-07-11

## Key classes

| Key | Purpose | Storage | Lifetime |
|-----|---------|---------|----------|
| `atlas-dev-package` | Sign development `.deb` packages | Developer workstation (encrypted) | Rotating, non-production |
| `atlas-release-package` | Sign production APT packages | Offline HSM or air-gapped smartcard | Annual rotation |
| `atlas-release-iso` | Sign ISO / OEM / recovery artefacts | Offline HSM | Annual rotation |
| `atlas-content-pack` | Sign `.atlas-pack` catalogues and packs | Release signing ceremony | Annual rotation |
| `atlas-update-metadata` | Sign update manifests | Same as release package | Tied to channel |

## Development policy

- Generate **dev** keys locally with `scripts/generate-dev-keys.sh`.
- Dev keys **must not** be trusted by production Secure Boot or production APT.
- Never commit private keys. Public keys may live under `release/keys/dev/`.
- CI uses ephemeral or injected secrets; no keys in the repository.

## Release policy

1. Build artefacts on a clean Debian builder from locked cache.
2. Generate checksums (SHA-256, SHA-512) and SPDX SBOM.
3. Sign `release.json` and artefacts with `atlas-release-*` keys.
4. Publish signature files alongside artefacts (`.sig`).
5. Installed systems verify signatures before applying updates or packs.

## Secure Boot

- V1 target: **compatibility** with vendor Secure Boot using Debian-signed shim where possible.
- Custom Atlas Secure Boot signing is **post-V1** unless OEM contract requires it earlier.

## Bootstrap commands (dev)

```bash
./scripts/generate-dev-keys.sh
# writes release/keys/dev/*.gpg and *.pem (public only to git)
```

## Verification

Installed systems store release public keys under `/usr/share/atlas/keys/`
(shipped from `packages/atlas-updater/usr/share/atlas/keys/`).

Preferred filenames (checked in order by `atlas-updater`):

1. `atlas-update-metadata.pub` — production update manifests  
2. `atlas-release-package.pub` — optional shared release key  
3. `atlas-dev-package.pub` — development only (`scripts/generate-dev-keys.sh`)

`atlas-updater` and `atlas-content-manager` refuse unsigned or unknown-publisher
payloads on **stable/release** unless `ATLAS_ALLOW_UNSIGNED=1` (alpha/dev).
`DEV-UNSIGNED-PLACEHOLDER` is never accepted on stable without that flag.

Until a release ceremony publishes `atlas-update-metadata.pub`, only the committed
dev public key is present — do **not** invent fake production secrets in-tree.
