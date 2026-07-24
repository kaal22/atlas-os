# Signing Key Plan

Status: Phase 1 — signed update bundles (dev path + ceremony hooks)  
Date: 2026-07-24

## Key classes

| Key | Purpose | Storage | Lifetime |
|-----|---------|---------|----------|
| `atlas-dev-package` | Sign development `.deb` / `.atlas-update` bundles | Developer workstation (encrypted) | Rotating, non-production |
| `atlas-release-package` | Sign production APT packages | Offline HSM or air-gapped smartcard | Annual rotation |
| `atlas-release-iso` | Sign ISO / OEM / recovery artefacts | Offline HSM | Annual rotation |
| `atlas-content-pack` | Sign `.atlas-pack` catalogues and packs | Release signing ceremony | Annual rotation |
| `atlas-update-metadata` | Sign update manifests (`checksums.sha256` inside `.atlas-update`) | Same as release package | Tied to channel |

## Development policy

- Generate **dev** keys locally with `scripts/generate-dev-keys.sh`.
- Dev keys **must not** be trusted by production Secure Boot or production APT.
- Never commit private keys. Public keys may live under `release/keys/dev/`.
- CI uses ephemeral or injected secrets; no keys in the repository.

## Operator flow (signed OS updates)

### 1. Generate keys (once per workstation / ceremony)

```bash
./scripts/generate-dev-keys.sh
# writes release/keys/dev/atlas-dev-package.{key,pub}
# PRIVATE .key is gitignored — do not commit it

# Ship the public key on appliances (already done for the committed .pub):
cp release/keys/dev/atlas-dev-package.pub \
   packages/atlas-updater/usr/share/atlas/keys/atlas-dev-package.pub
```

Production: generate `atlas-update-metadata` offline (HSM / air-gap). Install only the
`.pub` as `packages/atlas-updater/usr/share/atlas/keys/atlas-update-metadata.pub`.
**Never** invent or commit production private keys.

### 2. Build + sign a bundle

```bash
# Default: auto-sign with dev key when present
./scripts/build-release-update.sh --from 0.1.0 --to 0.1.1

# Explicit:
./scripts/build-release-update.sh --from 0.1.0 --to 0.1.1 --sign \
  --key release/keys/dev/atlas-dev-package.key

# Or sign an existing unsigned bundle:
./scripts/sign-update-bundle.sh build/release/atlas-update-0.1.0-to-0.1.1.atlas-update

# Production:
ATLAS_UPDATE_SIGNING_KEY=/secure/atlas-update-metadata.key \
  ./scripts/build-release-update.sh --from 0.1.0 --to 0.1.1 --sign
```

`sign-update-bundle.sh` replaces `DEV-UNSIGNED-PLACEHOLDER` with
`openssl dgst -sha256 -sign` of `checksums.sha256`, verifies against the matching
`.pub`, then repacks.

### 3. Publish

```bash
./scripts/publish-release.sh --from 0.1.0 --to 0.1.1 --channel stable
# passes through --sign / --key / --no-sign
```

### 4. Apply on appliance (no ALLOW_UNSIGNED)

Stable/release appliances verify against `/usr/share/atlas/keys/` and **refuse**
`DEV-UNSIGNED-PLACEHOLDER` unless `ATLAS_ALLOW_UNSIGNED=1` (alpha/dev only).

```bash
# Offline:
sudo atlas-apply-update /path/to/signed.atlas-update
# or Command Centre → System → Software updates / Import update file
```

Do **not** set `ATLAS_ALLOW_UNSIGNED` on production appliances.

## Release policy

1. Build artefacts on a clean Debian builder from locked cache.
2. Generate checksums (SHA-256, SHA-512) and SPDX SBOM.
3. Sign `release.json` and artefacts with `atlas-release-*` keys.
4. Sign `.atlas-update` bundles with `atlas-update-metadata` (or pass `--key`).
5. Publish signature files alongside artefacts (`.sig`) and the signed bundle + `channel.json`.
6. Installed systems verify signatures before applying updates or packs.

## Secure Boot

- V1 target: **compatibility** with vendor Secure Boot using Debian-signed shim where possible.
- Custom Atlas Secure Boot signing is **post-V1** unless OEM contract requires it earlier.

## Bootstrap commands (dev)

```bash
./scripts/generate-dev-keys.sh
# writes release/keys/dev/*.key (gitignored) and *.pub (public only to git)
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
