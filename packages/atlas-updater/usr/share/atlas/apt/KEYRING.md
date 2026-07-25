# Atlas APT archive keyring

Production and appliance images should install a **GPG** keyring at:

`/usr/share/keyrings/atlas-archive-keyring.gpg`

This is separate from the OpenSSL keys used for `.atlas-update` manifests
(`atlas-update-metadata` under `/usr/share/atlas/keys/`).

## Ceremony (do not invent production private keys in git)

1. On an offline signing host, generate a dedicated APT signing key (GnuPG).
2. Export the **public** keyring only:
   `gpg --export --export-options export-minimal KEYID > atlas-archive-keyring.gpg`
3. Install the `.gpg` onto images; never commit the private key.
4. Sign `Release` / produce `InRelease` when building the repo
   (`scripts/build-apt-repo.sh` with `ATLAS_APT_GPG_KEY`).

Dev/USB MVP may use `deb [trusted=yes] file:…` until a keyring is present.
See `docs/updates/OS_UPDATES.md` and `docs/signing/SIGNING_PLAN.md`.
