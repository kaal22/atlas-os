#!/usr/bin/env bash
# Phase 5 ISO: Phase 4 agent runtime + knowledge/RAG (Qdrant + embeddings).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Phase 5: knowledge and documents ==="
echo "Ensures knowledge service, Document Agent, and CC citation UI are present,"
echo "then invokes phase4-iso.sh (agent runtime + security + offline payload)."
echo

for need in \
  packages/atlas-knowledge/usr/lib/atlas/knowledge_service.py \
  packages/atlas-agent-runtime/usr/share/atlas/agents/atlas.document.json \
  packages/atlas-command-centre/usr/lib/atlas/command_centre.py
do
  if [[ ! -f "$ROOT/$need" ]]; then
    echo "ERROR: missing $need" >&2
    exit 1
  fi
done

# Quick telltales that Phase 5 code is present
if ! grep -q 'def embed_texts' "$ROOT/packages/atlas-knowledge/usr/lib/atlas/knowledge_service.py"; then
  echo "ERROR: knowledge_service.py missing embed_texts (Phase 5 pipeline)" >&2
  exit 1
fi
if ! grep -q 'openSource' "$ROOT/packages/atlas-command-centre/usr/lib/atlas/command_centre.py"; then
  echo "ERROR: command_centre.py missing citation/source viewer hooks" >&2
  exit 1
fi

export ATLAS_PHASE5=1
exec "$ROOT/scripts/phase4-iso.sh" "$@"
