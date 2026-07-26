# Arcalium OS — staged rebrand plan (Atlas OS → Arcalium OS)

> **Status:** Plan only — do not implement until this document is approved.  
> **Date:** 26 July 2026  
> **Repo inventory baseline:** `/home/kaal/Desktop/atlas-os` (excludes generated `chroot/`, `build/`, ISO binaries)  
> **Canonical product name:** **Arcalium** (short) / **Arcalium OS** (full)  
> **Slogan:** Your intelligence. Your knowledge. Anywhere.  
> **Meta title:** Arcalium OS | Private Offline AI Operating System  
> **Meta description:** Arcalium OS is a private, offline-first AI operating system with local agents, document search, maps, knowledge libraries and tools that work without the cloud.

Related docs: [`product.md`](../product.md) (header + §53), [`BACKLOG.md`](BACKLOG.md), [`PLAN.md`](PLAN.md), [`signing/SIGNING_PLAN.md`](signing/SIGNING_PLAN.md).

---

## Executive recommendation

| Track | Scope | When |
|-------|--------|------|
| **Milestone A — User-visible rebrand** (recommended first) | Strings, meta tags, wallpaper/SDDM labels, Calamares branding copy, boot menu labels, desktop names, Command Centre chrome, docs/README/`os-release` display names, ISO artifact filename, slogan | Next release / alpha cut |
| **Milestone B — Internal rename** (later) | `atlas-*` packages, `/usr/lib/atlas`, `/etc/atlas`, `/srv/atlas`, systemd units, `ATLAS_*` env, pack IDs, agent IDs, `.atlas-pack` / `.atlas-update` extensions, signing key *file* names | Separate release with migration + symlinks |

**Do not** rename pack IDs (`atlas.maps.uk`), agent IDs (`atlas.guide`), filesystem data root (`/srv/atlas`), or systemd unit names in Milestone A. Those break installed systems and content catalogues.

GitHub repo `kaal22/atlas-os` and historical commits: **optional / deferred**.

---

## 0. Inventory & principles

### Goal

Catalog every Atlas identity touchpoint and lock naming rules before any code moves.

### Naming rules

| Form | Use for |
|------|---------|
| **Arcalium OS** | Full product name (titles, `PRETTY_NAME`, Calamares `productName`, ISO labels, README H1) |
| **Arcalium** | Short product name (wordmarks, `NAME=`, Calamares `shortProductName`, wallpaper package display name, “Welcome to Arcalium”) |
| **arcalium** | Paths, package names, hostnames, IDs, env prefix *when* Milestone B lands (`/usr/lib/arcalium`, `arcalium-*`, `ARCALIUM_*`) |
| **ARCALIUM** | Env vars / constants *when* Milestone B lands; until then keep `ATLAS_*` for compatibility |
| **Arcalium OS Builders** | Maintainer string in Debian control (replace `Atlas OS Builders`) |

Slogan and meta title/description are fixed assets (see header). Apply slogan on Welcome wizard + About/marketing surfaces; apply meta tags on HTML shells that have `<title>` / marketing pages.

### Classification legend

1. **Must rename** — user-visible brand (copy, icons labels, wallpaper names, SDDM/GRUB text, wizard, meta).
2. **Should rename** — package/path/systemd consistency (high risk; needs migration + symlinks for ≥1 release).
3. **Defer / keep internal** — pack IDs, agent IDs, API route shapes, `/srv/atlas` data layouts, GitHub repo URL, historical commits, file extensions that are already on USB sticks.

### Inventory summary (source tree, excl. `chroot/` / `build/` / ISO blobs)

| Category | Scale / findings | Representative paths |
|----------|------------------|----------------------|
| **“Atlas OS” string** | ~70+ source files; heavy in `product.md`, boot hooks, Calamares, docs, scripts | `product.md`, `config/hooks/normal/9050-atlas-boot-menu.hook.binary`, `calamares/branding/atlas/branding.desc`, `README.md`, `docs/*` |
| **Command Centre UI** | ~83 “Atlas”/“atlas-” hits in one file | `packages/atlas-command-centre/usr/lib/atlas/command_centre_ui.html` (`<title>`, wordmark, Welcome, Library/Education/Maps labels) |
| **Debian packages** | **15** `packages/atlas-*` | `atlas-branding`, `atlas-shell`, `atlas-command-centre`, `atlas-firstboot`, `atlas-updater`, … |
| **Systemd units (source)** | **6** `atlas-*.service` | `atlas-command-centre`, `atlas-firstboot`, `atlas-payload`, `atlas-system-daemon`, `atlas-proxy`, `atlas-status` |
| **Binaries** | **5** under `*/usr/bin/atlas-*` | `atlas-launcher`, `atlas-health`, `atlas-qc`, `atlas-open-command-centre`, `atlas-gpu-setup` |
| **Live-build hooks** | **13** `*atlas*` hooks | `config/hooks/normal/9000-…` through `9050-…`, plus live installer icon hook |
| **Catalogue pack IDs** | **30** stable IDs `atlas.*` + schema `atlas.pack/v1` | `content/catalogues/catalogue.json` (+ mirrored under `packages/` and `config/includes.chroot/`) |
| **Pack / update files** | `*.atlas-pack`, `*.atlas-update` | e.g. `atlas-maps-uk.atlas-pack`, `atlas-update-0.1.0-to-0.1.1.atlas-update` |
| **Filesystem roots** | `/usr/lib/atlas`, `/usr/share/atlas`, `/etc/atlas`, `/srv/atlas`, `/run/atlas` | `atlas.conf`, compose mounts, firstboot, updater docs |
| **Env prefix** | `ATLAS_*` in **~60** `.py`/`.sh`/`.conf`/`.yml` files | `ATLAS_COMMAND_CENTRE_URL`, `ATLAS_DATA`, `ATLAS_ALLOW_UNSIGNED`, … |
| **os-release** | `NAME="Atlas OS"`, `ID=atlas`, `HOME_URL=https://atlas-os.local/` | `config/includes.chroot/etc/os-release` |
| **Live hostname** | `hostname=atlas-live`, `username=atlas` | `auto/config` `--bootappend-live` |
| **Wallpaper / icons** | Plasma package `wallpapers/Atlas`; backgrounds `…/backgrounds/atlas/atlas-*.png`; icons `atlas.png` / `atlas-services.*` | `config/includes.chroot/usr/share/wallpapers/Atlas/`, `assets/atlas-default.png`, `assets/atlas-wallpaper-master.png` |
| **SDDM** | Breeze theme + Atlas background via hook; config `10-atlas.conf` | `config/includes.chroot/etc/sddm.conf.d/10-atlas.conf`; hook `9030-atlas-wallpaper` |
| **Plymouth** | **Not customised** (stock) | noted in `docs/BACKLOG.md` / `product.md` §53.2 |
| **Calamares branding** | Component `atlas`; product strings “Atlas OS” / “Atlas” | `calamares/branding/atlas/`, packaged via `atlas-branding` → `/usr/share/atlas/calamares/` |
| **Ports (keep)** | CC `:8787`, Kiwix `:8080`, Ollama, etc. — **not brand** | `network_modes.py`, `atlas.conf` |
| **Meta title/description** | **Missing** today — CC title is `Atlas Command Centre`; no og/meta description | CC HTML, launcher HTML |
| **Signing keys** | Display/file names `atlas-dev-package`, `atlas-update-metadata`, APT `atlas-archive-keyring` | `docs/signing/SIGNING_PLAN.md`, `packages/atlas-updater/usr/share/atlas/keys/` |
| **GitHub** | `https://github.com/kaal22/atlas-os.git` | remote `origin` — defer rename |
| **ISO artifacts** | `atlas-os-${VERSION}-amd64.iso` | `scripts/build-iso.sh`, `phase1-iso.sh`, `dist/` |

### What stays for compatibility (Milestone A)

- Package names `atlas-*`
- Paths `/usr/lib/atlas`, `/usr/share/atlas`, `/etc/atlas`, `/srv/atlas`, `/run/atlas`
- Systemd unit filenames and `Requires=`/`After=` chains
- Pack IDs `atlas.maps.uk`, agent IDs `atlas.guide`, schema `atlas.pack/v1`
- File extensions `.atlas-pack`, `.atlas-update`
- Env vars `ATLAS_*` (unless introducing dual-read aliases later)
- Unix socket `/run/atlas/system.sock`
- Capability-token / Policy Gateway internals (unless user-facing error strings say “Atlas”)
- Live username `atlas` (optional later → `arcalium`; changing breaks skel/docs)
- Repo remote and CI workflow *filenames* (workflow *display* name can change)

### Done-when (Stage 0)

- [x] Inventory captured in this document
- [ ] Stakeholders agree Milestone A vs B split
- [ ] Asset drop locations agreed (logo PNG/SVG, wallpaper masters)

### Order / parallelization

Stage 0 gates all others. Stages 1–4 and 7–8 can largely proceed in parallel after principles lock. Stage 5–6 must wait for Milestone B decision.

---

## 1. Brand foundation

### Goal

Establish slogan, meta tags, logo/wallpaper ownership, and where new Arcalium assets live — without moving package paths.

### Key files / areas

| Area | Paths |
|------|--------|
| Source assets | `assets/atlas-default.png`, `assets/atlas-wallpaper-master.png` |
| Packaged logo | `packages/atlas-command-centre/usr/lib/atlas/atlas-logo.png`, launcher `…/launcher/logo.png` |
| Wallpaper package | `config/includes.chroot/usr/share/wallpapers/Atlas/metadata.json` + `contents/images/*` |
| Backgrounds | `config/includes.chroot/usr/share/backgrounds/atlas/atlas-*.png` |
| Branding package (thin) | `packages/atlas-branding/` (copies Calamares tree; Description still “Atlas OS”) |
| Color system | CC CSS variables in `command_centre_ui.html` (`--primary` indigo, cyan, amber) — keep unless new brand palette supplied |

### Work items

- [ ] Add canonical brand constants doc snippet (name, slogan, meta title, meta description) — this file is the plan; optionally a small `docs/BRAND.md` later
- [ ] Drop / rename master assets to Arcalium filenames **or** keep filenames and only change display metadata in Milestone A:
  - Preferred Milestone A: keep `atlas-*.png` on disk; change Plasma `metadata.json` Name/Description to **Arcalium OS**
  - Milestone B: `assets/arcalium-*.png`, `/usr/share/backgrounds/arcalium/`, wallpaper dir `Arcalium/`
- [ ] Produce (or commission) logo mark for CC/Calamares/SDDM; place under:
  - Source: `assets/arcalium-logo.png` (+ SVG if available)
  - Runtime (Milestone A): still install as `/usr/lib/atlas/atlas-logo.png` **or** dual-ship `arcalium-logo.png` and point UI at new path without renaming the directory
- [ ] Wire slogan into Welcome wizard + About surface
- [ ] Add HTML `<title>` + `<meta name="description">` (+ optional `og:title` / `og:description`) using exact meta strings
- [ ] Note Plymouth: still absent — Stage 2 can stub theme name `arcalium` when implemented

### Risks / migrations

- Replacing wallpaper PNGs without updating Plasma package hashes/paths breaks SDDM hook `9030-atlas-wallpaper`
- Logo path hardcoded as `/assets/atlas-logo.png` in CC UI — update references with asset drop

### Done-when

- [ ] Slogan and meta strings appear in at least one shipped HTML surface
- [ ] Wallpaper Plasma package displays **Arcalium OS** in chooser
- [ ] Asset ownership documented (who regenerates 1080p/1440p/4k)

### Order

First parallel track with Stage 2–4. Unblocks visual QA.

---

## 2. Desktop & shell branding

### Goal

Plasma wallpaper labels, icons, `.desktop` Names, SDDM greeter background labeling, GRUB identity, launcher chrome — user sees Arcalium, not Atlas.

### Key files / areas

| Surface | Paths |
|---------|--------|
| Wallpaper metadata | `config/includes.chroot/usr/share/wallpapers/Atlas/metadata.json` |
| Wallpaper helper / log | `/usr/lib/atlas/set-wallpaper.sh`, `/tmp/atlas-wallpaper.log` (script under packages/hooks) |
| Autostart | `atlas-wallpaper.desktop`, `atlas-launcher.desktop`, `atlas-trust-desktop.desktop` |
| Applications | `packages/atlas-command-centre/…/atlas-command-centre.desktop`, `packages/atlas-shell/…/atlas-launcher.desktop`, `atlas-gpu-setup.desktop` |
| Icons | `usr/share/icons/hicolor/*/apps/atlas.png`, `atlas-services.svg` |
| SDDM | `config/includes.chroot/etc/sddm.conf.d/10-atlas.conf`; Breeze `theme.conf.user` background (hook) |
| Launcher UI | `packages/atlas-shell/usr/share/atlas/launcher/index.html` (`<title>Atlas OS</title>`) |
| GRUB | `config/includes.chroot/etc/default/grub.d/atlas.cfg` |
| os-release | `config/includes.chroot/etc/os-release` |

### Work items

- [ ] Update Plasma wallpaper Name/Description → Arcalium OS + slogan-aware description
- [ ] Desktop `Name=` / `GenericName=` / `Comment=`: Command Centre, Service Check, GPU Setup, Installer → Arcalium wording (filenames may stay `atlas-*.desktop` in Milestone A)
- [ ] Launcher HTML title + H1 → **Arcalium OS**; inject meta description
- [ ] `os-release`: `NAME` / `PRETTY_NAME` → Arcalium OS; **keep `ID=atlas` in Milestone A** (or set `ID=arcalium` only if tooling does not key off it — verify live-build / apt Origin first). Prefer: `NAME="Arcalium OS"`, `ID=arcalium`, `ID_LIKE=debian`, update HOME/SUPPORT URLs to placeholder `arcalium.local` or real domain when known
- [ ] SDDM: no text brand today beyond wallpaper — ensure wallpaper is Arcalium art; optional future theme rename
- [ ] Icon theme: Milestone A can keep icon *names* `atlas` (desktop `Icon=atlas`) if artwork is replaced in place; Milestone B renames to `arcalium`
- [ ] Plymouth (optional stub): add theme package later; not blocking Milestone A

### Risks / migrations

- Changing `ID=` in `os-release` may affect scripts that match `ID=atlas` — grep before flip
- Autostart `.desktop` filenames with `atlas-` are invisible to users; low priority

### Done-when

- [ ] Fresh session: wallpaper chooser + desktop icons say Arcalium
- [ ] Service Check / launcher page shows Arcalium OS
- [ ] `cat /etc/os-release` shows Arcalium OS pretty name

### Order

Parallel with Stages 1 and 3. Depends on Stage 1 assets for visual swap.

---

## 3. Install / first-boot / setup wizard

### Goal

Live ISO, Calamares, boot menu, installer launchers, and first-run Welcome copy all say Arcalium OS.

### Key files / areas

| Surface | Paths |
|---------|--------|
| Boot menu | `config/hooks/normal/9050-atlas-boot-menu.hook.binary` (“Try Atlas OS”, “Install Atlas OS”) |
| Installer desktop | `config/hooks/normal/9001-atlas-installer-launcher.hook.chroot`, `config/hooks/live/9000-install-desktop-icon.hook.chroot`, `scripts/remaster-installer-default.sh` |
| Calamares branding | `calamares/branding/atlas/branding.desc`, `slideshow.qml`; mirrored under `config/includes.chroot/usr/share/atlas/calamares/` |
| Calamares settings | `calamares/settings.conf` |
| Live bootappend | `auto/config` (`username=atlas hostname=atlas-live`) |
| Firstboot | `packages/atlas-firstboot/…` (paths stay; Description strings) |
| Wizard state | `/srv/atlas/databases/first-run.json` via `command_centre.py` `WIZARD_STATE` — **path stays** |
| Wizard copy | `command_centre_ui.html` Welcome step: “Welcome to Atlas”, “Atlas is local-first…” |
| Phase scripts | `scripts/phase1-iso.sh` messaging |

### Work items

- [ ] Boot menu labels → **Try Arcalium OS** / **Install Arcalium OS** (GRUB + syslinux sections of `9050` hook)
- [ ] Installer `.desktop` Name/Comment → Install Arcalium OS
- [ ] Calamares `branding.desc`: `productName`, `shortProductName`, `versionedName`, `bootloaderEntryName` → Arcalium OS / Arcalium
- [ ] Slideshow QML text “Atlas OS” → “Arcalium OS”
- [ ] Optional Milestone A: live `hostname=arcalium-live` (keep `username=atlas` unless skel updated)
- [ ] Wizard Welcome: “Welcome to Arcalium”; body mentions Arcalium; show slogan under hero
- [ ] Home banner “Welcome to Atlas” → Arcalium
- [ ] Firstboot systemd `Description=` strings → Arcalium OS …
- [ ] Calamares `componentName: atlas` — **keep in Milestone A** (module path); rename folder in Milestone B with settings.conf update

### Risks / migrations

- Boot hook string replacements are brittle regexes — update both sed patterns and Python `menuentry` builders together
- Hostname change only affects live session; installed hostname comes from Calamares user module (verify default)

### Done-when

- [ ] ISO boot menu shows Install/Try Arcalium OS
- [ ] Calamares welcome shows Arcalium OS
- [ ] First-run Welcome step shows Arcalium + slogan
- [ ] No user-facing “Install Atlas OS” on live desktop

### Order

After Stage 1 copy constants; parallel with Stage 2. Needs ISO rebuild for acceptance.

---

## 4. In-app product surfaces

### Goal

Command Centre, Maps, Library, Education, agents’ *display* names, and About copy read as Arcalium.

### Key files / areas

| Surface | Paths |
|---------|--------|
| CC shell | `packages/atlas-command-centre/usr/lib/atlas/command_centre_ui.html` — wordmark “Atlas OS Command Centre”, `<title>` |
| Maps | aria-label “Atlas Maps”; `packages/atlas-maps-viewer/…/index.html`, `atlas-maps-app.js` |
| Library / Education | “Atlas Library”, “Atlas Education” strings |
| Agents (display) | UI: “Atlas Guide”; IDs remain `atlas.guide`, `atlas.research`, `atlas.system-steward` |
| Agent defs | `packages/atlas-agent-runtime/usr/share/atlas/agents/*.json` |
| Backend strings | `command_centre.py`, `agent_runtime.py` user-visible messages |
| Catalogue display | Pack `name` fields already generic (“United Kingdom Offline Maps”) — low Atlas leakage; schema/id stay |

### Work items

- [ ] CC `<title>` → meta title: **Arcalium OS | Private Offline AI Operating System** (or shorter in-app: **Arcalium Command Centre** with meta description set separately)
- [ ] Add `<meta name="description" content="…">` exact meta description
- [ ] Sidebar wordmark → **Arcalium OS** / Command Centre
- [ ] “Atlas Library” → “Arcalium Library” (or “Library” + powered-by line)
- [ ] “Atlas Education” → “Arcalium Education”
- [ ] “Atlas Maps” → “Arcalium Maps”
- [ ] “Atlas Guide” **display** → “Arcalium Guide” (keep `value="atlas.guide"`)
- [ ] Chat empty state / wizard agent copy
- [ ] Maps viewer HTML titles/NOTICE user-facing lines
- [ ] APT Origin / publisher display strings in updater UI if shown

### Risks / migrations

- Renaming agent **IDs** breaks `first-run.json`, chat store, tests, Policy Gateway — **do not** in Milestone A
- DOM ids like `atlasMapsHost` can stay (not user-visible)

### Done-when

- [ ] Grep of user-facing HTML/JS for `Atlas OS`, `Atlas Library`, `Atlas Maps`, `Welcome to Atlas` is clean (allow comments / test fixtures with care)
- [ ] Agents still run with `atlas.*` IDs
- [ ] Meta title + description present in CC head

### Order

Parallel with Stages 2–3. Highest UX impact per hour.

---

## 5. System identity (optional phased — Milestone B)

### Goal

Rename packages, paths, and units to `arcalium-*` with one-release compatibility shims.

### Key files / areas

| Layer | Current | Target |
|-------|---------|--------|
| Packages | 15× `atlas-*` | `arcalium-*` (+ `Provides:`/`Conflicts:`/`Replaces:` as needed) |
| Code paths | `/usr/lib/atlas`, `/usr/share/atlas` | `/usr/lib/arcalium`, `/usr/share/arcalium` |
| Config | `/etc/atlas`, `atlas.conf` | `/etc/arcalium`, `arcalium.conf` |
| Data | `/srv/atlas` | `/srv/arcalium` **or** keep `/srv/atlas` forever as data ABI |
| Runtime | `/run/atlas/system.sock` | `/run/arcalium/…` + symlink |
| Systemd | `atlas-*.service` | `arcalium-*.service` + `Alias=` / symlink units |
| Binaries | `atlas-*` | `arcalium-*` + symlinks |
| Env | `ATLAS_*` | `ARCALIUM_*` with dual-read for one release |
| Compose | `atlas-core.yml`, volume mounts | rename file + update firstboot |
| Hooks / package lists | `config/package-lists/atlas.list.chroot`, `900x-atlas-*.hook*` | rename for consistency |
| Nginx site | `atlas-command-centre` | `arcalium-command-centre` |
| APT | `Origin: Atlas OS`, `atlas.list.template`, `atlas-archive-keyring` | Arcalium equivalents |

### Work items

- [ ] Design migration matrix (old → new → symlink duration)
- [ ] Decide **/srv/atlas** policy:
  - **Option B1 (recommended):** keep `/srv/atlas` as stable data root forever; only rename display + packages
  - **Option B2:** migrate to `/srv/arcalium` with `mv` + bind-mount/symlink on upgrade; update all compose binds
- [ ] Package rename with transitional dummy packages
- [ ] Dual-load Python `sys.path` for `/usr/lib/atlas` and `/usr/lib/arcalium`
- [ ] Systemd `Alias=atlas-command-centre.service` during transition
- [ ] Update `scripts/dev-sync.manifest` (127 path refs today)
- [ ] Update all phase/evidence scripts and unit tests’ `sys.path` inserts
- [ ] Live username / hostname defaults

### Risks / migrations (highest)

| Risk | Why it hurts |
|------|----------------|
| **`/srv/atlas` rename** | MySQL, Qdrant, Kiwix, Kolibri, maps, nomad-storage, secrets, first-run.json, backups all keyed here |
| **Systemd unit rename** | Enables, WantedBy links, updater `restart_services` lists, evidence scripts |
| **`ATLAS_*` env** | 60+ files; compose `.env`; operator muscle memory |
| **Incomplete symlink coverage** | Partial rename → split-brain installs |

### Done-when

- [ ] Fresh install uses `arcalium-*` packages only
- [ ] Upgrade from Atlas-named alpha succeeds with data intact
- [ ] Symlink compatibility layer documented with removal target version

### Order

**After** Milestone A ships. Do **not** parallelize with content-ID changes. Requires dedicated release + soak.

---

## 6. Content & updates

### Goal

User-facing catalogue/update/publisher names say Arcalium; stable IDs and on-disk extensions stay until a versioned schema migration exists.

### Key files / areas

| Item | Current | Milestone A | Milestone B+ |
|------|---------|-------------|--------------|
| Pack IDs | `atlas.maps.uk`, … (30) | **keep** | optional `arcalium.*` with alias map in content-manager |
| Schema | `atlas.pack/v1` | **keep** | `arcalium.pack/v1` + reader accepts both |
| Pack filenames | `atlas-maps-uk.atlas-pack` | **keep** | dual extension or rename with installer rewrite |
| Update bundles | `.atlas-update`, publisher `"Atlas OS"` | change **publisher / notes** only | rename extension carefully |
| Signing keys | `atlas-dev-package`, `atlas-update-metadata` | change **docs display** / ceremony names; **keep key filenames** until ceremony rotation | new key names at next ceremony |
| APT Origin | `Atlas OS` | → `Arcalium OS` | keyring filename later |
| Agent IDs | `atlas.guide` etc. | display only | ID migration with state rewrite |

### Work items

- [ ] Milestone A: `scripts/build-release-update.sh` publisher + release notes → Arcalium OS
- [ ] Milestone A: APT `Origin: Arcalium OS` in `scripts/build-apt-repo.sh`
- [ ] Milestone A: Maintainer strings in generated debs
- [ ] Document pack-ID freeze in BACKLOG / this plan
- [ ] Milestone B design: content-manager alias table `atlas.*` ↔ `arcalium.*`
- [ ] Do **not** wholesale-rename `.atlas-pack` on USB media without a migration tool

### Risks / migrations

- Changing pack IDs orphans installed packs and breaks catalogue diffs
- Renaming update extension breaks CC browse filters and docs
- Key filename change without shipping new `.pub` breaks signature verify

### Done-when

- [ ] New update notes say Arcalium OS
- [ ] Existing packs still install by `atlas.*` id
- [ ] Written decision: pack IDs frozen through at least next major

### Order

Milestone A publisher strings parallel with Stage 4. ID migration only with Stage 5.

---

## 7. Docs & marketing

### Goal

Spec, user docs, backlog, and README speak Arcalium; implementation status notes the rename.

### Key files / areas

- `product.md` — title, working title, §1, §53 branding leftovers, line about “stored only in branding configuration”
- `README.md`
- `docs/BACKLOG.md`, `docs/PLAN.md`, `docs/user/*`, `docs/updates/*`, `docs/signing/*`, `docs/threat-model/*`, `docs/legal/*`
- `.github/workflows/ci.yml` workflow `name:`
- In-tree GPU/OS update docs under `usr/share/atlas/docs/`
- `content/packs/.../geography-world.md` (mentions Atlas OS offline maps)
- Website (if external) — apply meta title/description exactly

### Work items

- [ ] Rewrite product header: working title **Arcalium OS**; keep historical “derived from N.O.M.A.D.” language
- [ ] §53 / BACKLOG: add rebrand checklist pointer to this plan; retitle polish items
- [ ] README H1 + blurb + slogan
- [ ] User GETTING_STARTED: Install Arcalium OS
- [ ] Legal attribution: “Arcalium OS is based on Debian…”
- [ ] CI workflow display name
- [ ] Optional: website meta tags (exact strings from brand assets)
- [ ] Note deferred: GitHub repo rename `atlas-os` → `arcalium-os` (breaks clone URLs, badges, update endpoint defaults that point at GitHub Releases)

### Risks / migrations

- Default update endpoint may hardcode GitHub `kaal22/atlas-os` — inventory before repo rename
- Spec churn: prefer one editorial pass after UI freeze

### Done-when

- [ ] Top-level docs say Arcalium OS
- [ ] This plan linked from BACKLOG / PLAN
- [ ] Repo rename listed as deferred with owners

### Order

Can start anytime; finalize after Milestone A string freeze. Parallel-safe.

---

## 8. ISO / release

### Goal

Release artifacts and publish messaging use `arcalium-os-*.iso` without breaking checksum scripts.

### Key files / areas

- `scripts/build-iso.sh`, `phase1-iso.sh` … `phase7-iso.sh`, `remaster-installer-default.sh`, `test-release.sh`, `publish-release.sh`
- `Makefile` targets / help text
- `dist/atlas-os-0.1.0-alpha-amd64.iso*` (historical artifacts — leave; new builds new names)
- `auto/config` live-build ISO volume labels if any
- Version bump: product still `0.1.0-alpha` unless release manager bumps for brand cut

### Work items

- [ ] Change `ISO_NAME` pattern → `arcalium-os-${VERSION}-amd64.iso`
- [ ] Update publish-release titles: `Arcalium OS v…`
- [ ] Update CI artifact names if uploaded
- [ ] Decide version policy: brand-only cut can keep `0.1.0-alpha` or tag `0.1.1-alpha` for clarity
- [ ] Refresh sha256/sha512 generation paths
- [ ] SBOM / sources.catalog Origin strings

### Risks / migrations

- External docs/bookmarks pointing at old ISO filenames
- Remaster scripts assuming `atlas-os-` prefix

### Done-when

- [ ] `make iso` (or phase script) emits `arcalium-os-*.iso` + checksums
- [ ] GitHub Release title uses Arcalium OS
- [ ] Smoke: UEFI boot → Install Arcalium OS → desktop brand check

### Order

After Stages 2–4 strings land (so ISO QA validates brand). Parallel with Stage 7 editorial.

---

## 9. Verification checklist

### Goal

Prove no leftover **user-facing** “Atlas OS” / “Atlas Library” / “Welcome to Atlas” on a VM or fresh ISO.

### Work items (checkable)

**Static**

- [ ] `rg -n 'Atlas OS|Welcome to Atlas|Atlas Library|Atlas Maps|Atlas Education|Install Atlas OS|Try Atlas OS' packages/ config/ calamares/ docs/ README.md product.md scripts/ --glob '!**/chroot/**'`
- [ ] Confirm remaining `atlas` hits are paths, IDs, package names, or deferred items only
- [ ] Unit tests green (`tests/unit`, security tests) after string-only edits
- [ ] Pack catalogue still validates (`make catalog` / pack manifest tests)

**Runtime (VM / ISO)**

- [ ] Boot menu: Install / Try **Arcalium OS**
- [ ] Calamares product name Arcalium OS
- [ ] SDDM/Plasma wallpaper shows Arcalium art / label
- [ ] Desktop launchers: Command Centre / Service Check branded
- [ ] CC `:8787` — title, wordmark, Welcome + slogan, Library/Education/Maps labels
- [ ] `os-release` pretty name
- [ ] Setup wizard completes; `first-run.json` still under `/srv/atlas/databases/`
- [ ] Install one existing pack by id `atlas.maps.uk` (or stub) — proves IDs unchanged
- [ ] Apply sample `.atlas-update` if present — publisher string may say Arcalium; format unchanged
- [ ] `systemctl is-active atlas-command-centre` still works (Milestone A)

### Done-when

- [ ] Checklist signed off on one fresh ISO or `dev-pull` VM
- [ ] Known exceptions list committed (paths/IDs kept)

### Order

Last gate for Milestone A. Parallelizable static vs runtime.

---

## Recommended first milestone (Milestone A)

**User-visible rebrand without breaking package paths**

Ship together:

1. Stage 1 — slogan + meta + wallpaper display names (+ logo art if ready)
2. Stage 2 — desktop / launcher / os-release display
3. Stage 3 — boot menu, Calamares strings, wizard Welcome
4. Stage 4 — Command Centre / Maps / Library / Education display strings
5. Stage 6 (partial) — publisher / APT Origin / release notes only
6. Stage 7 — docs/README/product header
7. Stage 8 — `arcalium-os-*.iso` naming
8. Stage 9 — verification

**Explicitly out of scope for Milestone A:** Stages 5 full path/package rename; pack/agent ID changes; `/srv/atlas` move; GitHub repo rename; `.atlas-pack` extension; Plymouth (unless cheap stub).

### Full internal rename (Milestone B) — later

Stage 5 + Stage 6 ID/extension migration + key ceremony renames. Prefer **keeping `/srv/atlas`** (Option B1) unless there is a hard trademark/path requirement.

---

## Biggest risks (callouts)

1. **Pack IDs (`atlas.maps.uk`, schema `atlas.pack/v1`)** — renaming breaks catalogues, installed state, USB packs, and tests. Freeze until an alias layer exists.
2. **`/srv/atlas` data root** — compose, databases, maps, Kiwix, Kolibri, first-run, backups. Highest migration cost; recommend permanent keep or long symlink.
3. **Systemd `atlas-*.service` + updater restart lists** — rename without aliases bricks boot services and update apply.
4. **Boot menu hook regexes** — easy to half-update and leave mixed “Atlas”/“Arcalium” entries.
5. **GitHub `kaal22/atlas-os` + default update endpoint** — repo rename is optional and cascades to Releases URLs; defer until endpoint config is parameterized.

---

## Suggested timeline (indicative)

| Week | Focus |
|------|--------|
| 0 | Approve this plan; drop logo/wallpaper if new art exists |
| 1 | Milestone A Stages 1–4 strings + assets |
| 1–2 | Docs + ISO rename + Stage 9 VM/ISO QA |
| Later | Milestone B design review → implement with transitional packages |

---

## Appendix A — Agent & pack ID freeze list (do not rename in Milestone A)

**Agents:** `atlas.guide`, `atlas.research`, `atlas.system-steward`

**Pack ID prefixes:** `atlas.maps.*`, `atlas.models.*`, `atlas.education.*`, `atlas.knowledge.*`

**Extensions:** `.atlas-pack`, `.atlas-update`

**Sockets / modes:** `/run/atlas/system.sock`, `/etc/atlas/network-mode`, `first-run.json` location under `/srv/atlas/databases/`

## Appendix B — Exact brand strings to apply

```
Product:     Arcalium
Full:        Arcalium OS
Slogan:      Your intelligence. Your knowledge. Anywhere.
Meta title:  Arcalium OS | Private Offline AI Operating System
Meta desc:   Arcalium OS is a private, offline-first AI operating system with local agents, document search, maps, knowledge libraries and tools that work without the cloud.
```

## Appendix C — Cross-links to update when implementing

- Add checkbox under `docs/BACKLOG.md` → Desktop polish & branding pointing here
- Note in `docs/PLAN.md` Milestone 2+ / polish
- `product.md` §53.2 P1 branding + working title line (~3405) and header

---

*End of plan. Implementation requires explicit go-ahead beyond committing this document.*
