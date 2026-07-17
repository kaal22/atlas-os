#!/usr/bin/env bash
# Collect Phase 5 knowledge/RAG evidence on an installed Atlas OS system.
set -euo pipefail

OUT="${1:-/srv/atlas/logs/phase5-evidence.txt}"
mkdir -p "$(dirname "$OUT")"
{
  echo "=== Phase 5 evidence $(date -Is) ==="
  echo
  echo "-- Qdrant --"
  curl -sS --max-time 3 http://127.0.0.1:6333/readyz || echo "qdrant_unreachable"
  echo
  echo "-- Ollama tags (expect chat + nomic-embed-text for hybrid) --"
  curl -sS --max-time 3 http://127.0.0.1:11434/api/tags || echo "ollama_unreachable"
  echo
  echo "-- Knowledge status (auth may 401 — check after login) --"
  curl -sS -o /dev/null -w "knowledge_status_http=%{http_code}\n" --max-time 3 \
    http://127.0.0.1/api/knowledge/status || true
  echo
  echo "-- systemd --"
  systemctl is-active atlas-command-centre.service ollama.service 2>/dev/null || true
  echo
  echo "-- agents (expect atlas.document.json) --"
  ls -la /usr/share/atlas/agents/ 2>/dev/null || true
  echo
  echo "-- knowledge + backups dirs --"
  ls -la /srv/atlas/knowledge /srv/atlas/backups/knowledge 2>/dev/null || echo "dirs missing"
  echo
  echo "Manual: login → Knowledge → import a .md → Chat with Document/Guide → expect Sources."
  echo "Manual: second user must not see first user's library (cross-user isolation)."
} | tee "$OUT"

echo "Wrote $OUT"
