#!/usr/bin/env bash
# Phase 3 ISO: Phase 2 payload + identity/security packages (auth, proxy, daemon).
# Rebuilds the hybrid ISO with Phase 3 services enabled via hooks/packages.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Phase 3: identity & security overlay ==="
echo "Builds Atlas .debs (incl. atlas-proxy, atlas-auth, atlas-command-centre, atlas-system-daemon),"
echo "then invokes phase2-iso.sh (payload + live-build)."
echo

# Fail early if nginx is not listed
if ! grep -q '^nginx$' "$ROOT/config/package-lists/atlas.list.chroot"; then
  echo "ERROR: nginx missing from atlas.list.chroot" >&2
  exit 1
fi

if [[ ! -f "$ROOT/config/hooks/normal/9030-atlas-phase3-services.hook.chroot" ]]; then
  echo "ERROR: Phase 3 services hook missing" >&2
  exit 1
fi

export ATLAS_PHASE3=1
exec "$ROOT/scripts/phase2-iso.sh" "$@"
