# Atlas OS — backlog

Actionable leftovers after recent main-line work. Check boxes as items land.

Phased plan summary: [`docs/PLAN.md`](PLAN.md).

## Done recently (on main / M1)

- Maps viewer (labels, search, roads)
- Content packs + Wikipedia SKUs
- Kids learning; Library / Education surfaces
- `:8787` launcher fix (Command Centre defaults to direct CC, not `:80`)
- **M1** — `:8787` canonical decision documented; wallpaper SDDM + helper hardening; stable unsigned gate; CC update UX; signing unit tests (see below)

## Milestone 1 status

| Item | Status |
|------|--------|
| `:8787` canonical (proxy optional) | Done — docs/PLAN, GETTING_STARTED, proxy comments, evidence script |
| Wallpaper live/installed path | Done in-tree — confirm on next ISO boot (checklist below) |
| Stable refuses unsigned | Done — `updater.verify_signature` + apply helper |
| CC update UX (channel / from→to / errors) | Done — System → Software updates |
| Updater signing unit tests | Done — `tests/unit/test_updater_signing.py` |
| Plan / BACKLOG merge | Done — `docs/PLAN.md` |

### Wallpaper verify checklist (no full ISO required for code review)

On a live or installed Plasma session:

- [ ] `/usr/lib/atlas/set-wallpaper.sh` is executable; assets exist under `/usr/share/backgrounds/atlas/*.png`
- [ ] Plasma package tree `/usr/share/wallpapers/Atlas/contents/images/` has 1920×1080 (and optional 1440p/4k)
- [ ] Autostart: `/etc/xdg/autostart/atlas-wallpaper.desktop` and skel copy
- [ ] SDDM: `/usr/share/sddm/themes/breeze/theme.conf.user` `background=` points at Atlas PNG (hook `9030-atlas-wallpaper`)
- [ ] After login, desktop shows Atlas wallpaper (or run `/usr/lib/atlas/set-wallpaper.sh` and check `/tmp/atlas-wallpaper.log`)

## What's left

### Content & education

- [x] **Kolibri / Khan / K-12 one-click catalogue channels** — locked Studio IDs as `atlas.education.kolibri-*` packs; Education CC one-click prepare + open Kolibri / USB import (media not in ISO)
- [x] **Licence audit** for those channels before bundling (`docs/legal/LICENCE_INVENTORY.md` + `CHANNELS.lock.yaml` + `licences.lock.yaml`)
- [x] **ZIM HTML → agent RAG** — selective extract (`meta.zim_rag`, zimdump/libzim or `rag-html` seed) into knowledge index; large ZIMs still `confirm_large`
- [x] **Kids expand URL** — pinned `file:///usr/share/atlas/content/kids-home-learning-expand.tar.gz` + GitHub raw fallback; `ATLAS_KIDS_EXPAND_URL` override

### Maps

- [x] **Map zoom > 11 / denser extracts** — default maxzoom 12; small countries z13; large countries stay z11 (opt-in via `ATLAS_PMTILES_MAXZOOM`); size hints + warnings updated

### Desktop polish & branding

- [x] **Wallpaper wiring (M1)** — helper, hook, SDDM `theme.conf.user`, autostart; ISO visual confirm still open
- [ ] **Wallpaper confirmed on ISO** — verify Plasma wallpaper applies live + installed (checklist above)
- [ ] **Theme polish** — Plasma look-and-feel, Command Centre UI, and shell (`atlas-launcher`) visual polish so the desktop reads as Atlas, not stock Breeze
- [ ] **Custom splash screens** — brand boot / login surfaces (Atlas today uses SDDM + Breeze + wallpaper symlink; no custom Plymouth theme yet):

  | Surface | Current | Paths / notes |
  |---------|---------|---------------|
  | SDDM greeter | Theme `breeze` + `theme.conf.user` Atlas background | `config/includes.chroot/etc/sddm.conf.d/10-atlas.conf`; hook `9030-atlas-wallpaper.hook.chroot` |
  | Plasma session wallpaper | Helper + Atlas wallpaper package | `/usr/lib/atlas/set-wallpaper.sh`, `/usr/share/backgrounds/atlas/*.png` |
  | Live / installed GRUB | Menu labels + `os-release` | `9050-atlas-boot-menu.hook.binary`, `/etc/default/grub.d/atlas.cfg` |
  | Calamares installer | Atlas branding | `/usr/share/atlas/calamares/branding/atlas` |
  | Plymouth (boot splash) | Not customised | Add branded Plymouth theme if desired for installed boot |

### Updates (production path)

Phase 7 MVP exists; signed-bundle path is wired for CI/dev (real production key still ceremony-only).

**Already there**

- `atlas-updater`: offline `.atlas-update` bundles, checksums, snapshot + health-check rollback (`packages/atlas-updater/`)
- Command Centre System UI: check / download / apply + local bundle browse (`/api/updates/*`) with channel + from→to messaging
- Online channel default: GitHub Releases `channel.json` (`DEFAULT_UPDATE_ENDPOINT` in `updater.py`; override via `/etc/atlas/update-endpoint`)
- Bundle builders: `scripts/build-update-bundle.sh`, `scripts/build-release-update.sh`
- **Signed bundles:** `scripts/sign-update-bundle.sh` + `--sign`/`--key` on build/publish (default auto-sign with dev key when present); operator steps in `docs/signing/SIGNING_PLAN.md`
- Signing plan: `docs/signing/SIGNING_PLAN.md` (`atlas-update-metadata`); public keys under `/usr/share/atlas/keys/`
- **M1:** stable/release refuse `DEV-UNSIGNED-PLACEHOLDER` unless `ATLAS_ALLOW_UNSIGNED=1`
- Disk preflight + atomic `.partial` download with retry/resume in `updater.download_bundle` / apply
- ISO gate: `scripts/phase7-iso.sh` (backup + updater + CC routes + sample/broken-rollback bundles)

**Gaps for proper OS updates**

- [x] **Refuse unsigned on stable (M1)** — gate + unit tests; production `atlas-update-metadata.pub` still pending release ceremony
- [x] **Command Centre update UX (M1 thin)** — channel, from/to version, apply/rollback/signature messaging
- [x] **Dev/CI signed update path** — `sign-update-bundle.sh`, build/publish `--sign`, signing round-trip tests
- [ ] **Signed production updates** — real release keys at ceremony (not inventing secrets in-tree); publish `atlas-update-metadata.pub`
- [x] **Download/apply reliability (practical slice)** — disk-space preflight, atomic `.partial` + retry/resume; full hardware rollback proof still open
- [ ] **Beyond GitHub Releases MVP** — signed APT / release channel suitable for appliances (product Phase 7: signed APT repo, app bundles, recovery ISO)
- [ ] Close V1 criterion #11 (update rollback automated tests) and commercial signing/recovery proof (`docs/user/V1_CRITERIA.md`)
- [ ] Prove rollback on real hardware / post-apply health under load

### Final ISO

- [ ] **Final ISO build** via `scripts/phase7-iso.sh` (or `make iso` / phase chain as appropriate for the release cut)

  Brief verification checklist:

  - [ ] Hybrid ISO boots (UEFI + BIOS)
  - [ ] Calamares install completes offline
  - [ ] Wallpaper + SDDM branding visible
  - [ ] Command Centre on `http://127.0.0.1:8787/`
  - [ ] Maps / education / knowledge packs present as locked
  - [ ] Update check + offline bundle apply (or dry-run) works
  - [ ] Checksums / SBOM / signatures as required for the release channel

### Ops

- [x] **atlas-proxy vs `:8787` for appliances (M1)** — decision: direct CC `:8787` canonical; `atlas-proxy` optional/compat; docs + launchers aligned
- [ ] **CI** — automated verify-cache / unit / security / ISO smoke as far as the builder allows
