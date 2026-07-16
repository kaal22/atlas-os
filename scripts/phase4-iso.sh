#!/usr/bin/env bash
# Phase 4 ISO: Phase 3 security + agent runtime (CPU/Ollama).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Phase 4: agent runtime (CPU-first) ==="
echo "Builds Atlas .debs (agent-runtime, policy-gateway, model-manager, command-centre),"
echo "then invokes phase3-iso.sh (identity/security + phase2 payload)."
echo

for need in \
  packages/atlas-agent-runtime/usr/lib/atlas/agent_runtime.py \
  packages/atlas-agent-runtime/usr/lib/atlas/tool_registry.py \
  packages/atlas-model-manager/usr/lib/atlas/model_router.py
do
  if [[ ! -f "$ROOT/$need" ]]; then
    echo "ERROR: missing $need" >&2
    exit 1
  fi
done

export ATLAS_PHASE4=1
exec "$ROOT/scripts/phase3-iso.sh" "$@"
