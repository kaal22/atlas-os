# Arcalium OS package updates (APT) vs application bundles

Status: Phase 1 scaffold (2026-07-25)  
Related: [`docs/signing/SIGNING_PLAN.md`](../signing/SIGNING_PLAN.md), [`docs/BACKLOG.md`](../BACKLOG.md)

## Two update tracks

| | `.atlas-update` (app bundle) | APT / OS packages (this track) |
|--|------------------------------|--------------------------------|
| **What** | Tar.gz of files under `/usr/lib/atlas`, `/srv/atlas`, … | Debian `.deb` packages via `apt` |
| **Who** | `atlas-updater` / `atlas-apply-update.py` | `os_updater.py` / `atlas-os-apt.py` |
| **Rollback** | Snapshot + health-check restore | `apt` history / reinstall previous `.deb` (phase 1: no auto snapshot) |
| **Signing** | OpenSSL over `checksums.sha256` (`atlas-update-metadata`) | GPG keyring `atlas-archive-keyring.gpg` for `Release`/`InRelease` |
| **CC API** | `/api/updates/*` | `/api/updates/os/*` (separate) |
| **Typical use** | Fast app/UI hotfixes without full package rebuild | Ship versioned `atlas-*` debs; later Debian security |

Do **not** mix them: applying a `.atlas-update` does not run `apt`, and APT does not unpack `.atlas-update` payloads.

## Phase 1 (shipping now)

1. Build Atlas `.deb`s: `./scripts/build-debs.sh`
2. Build a **local** APT repo: `./scripts/build-apt-repo.sh`
3. Copy `dist/apt-repo` to the device as `/srv/atlas/apt-repo` **or** USB folder `atlas-apt-repo/`
4. Enable source (privileged):  
   `sudo python3 /usr/lib/atlas/atlas-os-apt.py enable-source /srv/atlas/apt-repo`
5. Command Centre → System → **OS package updates**: Check / Apply  
   - Check: `apt-get update` + list upgradable **`atlas-*` only**  
   - Apply: `apt-get install --only-upgrade` those packages  
6. Privileged apply uses `systemd-run` + `ProtectSystem=false` (same as app-bundle apply), because Command Centre runs with `ProtectSystem=strict`.

### Signing ceremony (APT)

- **Do not** invent or commit production private keys.
- Export public keyring to `/usr/share/keyrings/atlas-archive-keyring.gpg` (see `packages/atlas-updater/usr/share/atlas/apt/KEYRING.md`).
- Sign repos with `ATLAS_APT_GPG_KEY=… ./scripts/build-apt-repo.sh`.
- Until a keyring is installed, local/USB repos may use `deb [trusted=yes] file:…` (dev/offline only).

OpenSSL `atlas-dev-package` / `atlas-update-metadata` keys remain for **`.atlas-update`** bundles only.

## Phase 2 (documented, not auto-shipped)

- Full Debian / security upgrades (`apt-get upgrade` or `full-upgrade`).
- **Never** automatic: requires owner role + explicit confirm **and** `ATLAS_OS_ALLOW_FULL_UPGRADE=1` on the apply helper.
- Prefer a remote signed HTTPS APT mirror when hosting is ready; until then USB/local file repos are the supported path.
- Stronger privilege model: extend `atlas-system-daemon` with dedicated apt capabilities and relaxed `ProtectSystem` only for that path (today CC uses one-shot `systemd-run`).

## Safety

- Whitelist reporting/apply for `atlas-*` in phase 1.
- CSRF + owner/admin on mutating CC routes.
- No private keys in git.
- Full-system upgrade gated as above.
