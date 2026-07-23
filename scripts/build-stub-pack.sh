#!/usr/bin/env bash
# Backward-compatible wrapper — builds default content packs (maps + knowledge).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/scripts/build-content-packs.sh" "$@"
