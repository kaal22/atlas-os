# Atlas OS user documentation (Phase 8)

## Install

1. Write the hybrid ISO to USB (balenaEtcher, `dd`, or Rufus in DD mode).
2. Boot UEFI, choose **Install Atlas OS**.
3. Prefer full-disk encryption when prompted.
4. Reboot into the installed system.

## First run

The Setup wizard guides hardware analysis, privacy mode, AI profile, content packs,
sharing mode, agents, and recovery key storage. Core features work offline after
provisioning.

## Daily use

Open **Atlas** from the desktop (or http://127.0.0.1:8787/ on the device).
Sign in with the account created at install / first run.

## Offline maps

1. In Command Centre open **Content**.
2. Install a country map pack (for example **United Kingdom**). Confirm the large download if prompted.
3. Wait until the progress panel shows tiles **ready** (this can take a while on first fetch).
4. Open **Maps** in the sidebar, or click **Open map** on the installed pack.

Direct links after sign-in:

- Maps (full page): http://127.0.0.1:8787/maps/?country=uk
- Command Centre Maps sidebar redirects to that URL when tiles are ready
- Debug: http://127.0.0.1:8787/maps/?country=uk&debug=1 or http://127.0.0.1:8787/maps/diag

Maps are viewed inside Atlas (MapLibre + PMTiles from `/srv/atlas/maps`). You do not need to open NOMAD separately.

## Backup and recovery

Use Command Centre → Backups. Keep recovery keys offline.
Recovery media can repair the system partition without wiping `/srv/atlas` personal data when using the preserve-data factory reset mode.

## Display server

Atlas defaults to **X11** (not Wayland) for NVIDIA and desktop compatibility.
Login session: **Plasma (X11)**.


If you have an NVIDIA GPU, install drivers so Ollama is fast:

```bash
atlas-gpu-setup --check
sudo atlas-gpu-setup --install-nvidia   # then reboot
```

Offline guide: `/usr/share/atlas/docs/GPU_SETUP.md` (also in Command Centre → System).
Without drivers, Atlas still works on CPU — use Tiny/Light model profiles.
