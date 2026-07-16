#!/usr/bin/env bash
# Collect Phase 4 agent-runtime evidence on an installed Atlas OS system.
set -euo pipefail

OUT="${1:-/srv/atlas/logs/phase4-evidence.txt}"
mkdir -p "$(dirname "$OUT")"
{
  echo "=== Phase 4 evidence $(date -Is) ==="
  echo
  echo "-- Ollama tags --"
  curl -sS --max-time 3 http://127.0.0.1:11434/api/tags || echo "ollama_unreachable"
  echo
  echo "-- Model recommend (via CC loopback or proxy) --"
  curl -sS -o /dev/null -w "health_http=%{http_code}\n" --max-time 3 http://127.0.0.1/api/system/health || true
  echo
  echo "-- systemd --"
  systemctl is-active atlas-command-centre.service ollama.service 2>/dev/null || true
  echo
  echo "-- agents on disk --"
  ls -la /usr/share/atlas/agents/ 2>/dev/null || true
  echo
  echo "-- memory tree --"
  ls -la /srv/atlas/memory 2>/dev/null || echo "no memory yet"
  echo
  echo "Manual: login at http://127.0.0.1/ then POST /api/ask with Guide."
  echo "Expect completed answer on CPU Ollama, or ollama_unavailable if model missing."
} | tee "$OUT"

echo "Wrote $OUT"
