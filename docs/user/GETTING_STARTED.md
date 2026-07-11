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

## Backup and recovery

Use Command Centre → Backups. Keep recovery keys offline.
Recovery media can repair the system partition without wiping `/srv/atlas` personal data when using the preserve-data factory reset mode.

## GPU / NVIDIA for local AI

If you have an NVIDIA GPU, install drivers so Ollama is fast:

```bash
atlas-gpu-setup --check
sudo atlas-gpu-setup --install-nvidia   # then reboot
```

Offline guide: `/usr/share/atlas/docs/GPU_SETUP.md` (also in Command Centre → System).
Without drivers, Atlas still works on CPU — use Tiny/Light model profiles.
