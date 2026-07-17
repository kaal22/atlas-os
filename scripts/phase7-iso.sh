#!/usr/bin/env bash
# Phase 7 ISO: backup + offline updates (then Phase 6 content packs).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Phase 7: updates, backup and recovery (MVP) ==="
echo "Ensures backup_service, updater, and CC System backup/update UI are present,"
echo "then invokes phase6-iso.sh (content packs + phase5 knowledge)."
echo

for need in \
  packages/atlas-backup/usr/lib/atlas/backup_service.py \
  packages/atlas-updater/usr/lib/atlas/updater.py \
  packages/atlas-command-centre/usr/lib/atlas/command_centre.py
do
  if [[ ! -f "$ROOT/$need" ]]; then
    echo "ERROR: missing $need" >&2
    exit 1
  fi
done

if ! grep -q 'def create_backup' "$ROOT/packages/atlas-backup/usr/lib/atlas/backup_service.py"; then
  echo "ERROR: backup_service.py missing create_backup" >&2
  exit 1
fi
if ! grep -q 'def apply_update' "$ROOT/packages/atlas-updater/usr/lib/atlas/updater.py"; then
  echo "ERROR: updater.py missing apply_update" >&2
  exit 1
fi
if ! grep -q '/api/backup/list' "$ROOT/packages/atlas-command-centre/usr/lib/atlas/command_centre.py"; then
  echo "ERROR: command_centre.py missing backup API routes" >&2
  exit 1
fi
if ! grep -q '/api/updates/apply' "$ROOT/packages/atlas-command-centre/usr/lib/atlas/command_centre.py"; then
  echo "ERROR: command_centre.py missing updates API routes" >&2
  exit 1
fi

echo "=== Building sample update bundles ==="
"$ROOT/scripts/build-update-bundle.sh"

if [[ ! -f "$ROOT/config/includes.chroot/usr/share/atlas/updates/atlas-update-broken-rollback.atlas-update" ]]; then
  echo "ERROR: broken rollback bundle not staged in includes" >&2
  exit 1
fi

export ATLAS_PHASE7=1
exec "$ROOT/scripts/phase6-iso.sh" "$@"
