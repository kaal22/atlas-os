#!/usr/bin/env bash
# Collect Phase 2 offline evidence on an installed Atlas OS system (or VM).
# Usage: sudo ./scripts/collect-phase2-evidence.sh [outdir]
set -euo pipefail

OUT="${1:-tests/installer/evidence/phase2-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT"

{
  echo "=== date ==="
  date -u
  echo "=== hostname ==="
  hostname || true
  echo "=== firstboot ==="
  ls -la /etc/atlas/firstboot-* 2>/dev/null || true
  cat /srv/atlas/logs/firstboot.json 2>/dev/null || echo "(no firstboot.json)"
  cat /srv/atlas/logs/payload-import.json 2>/dev/null || echo "(no payload-import.json)"
} | tee "$OUT/status.txt"

{
  echo "=== docker images ==="
  docker images 2>/dev/null || echo "docker unavailable"
  echo "=== docker compose ps ==="
  if [[ -f /srv/atlas/compose/atlas-core.yml ]]; then
    docker compose -f /srv/atlas/compose/atlas-core.yml ps 2>/dev/null || true
  fi
} | tee "$OUT/docker.txt"

{
  echo "=== listening sockets (ss) ==="
  ss -lntp 2>/dev/null || netstat -lntp 2>/dev/null || true
  echo
  echo "=== non-loopback docker publishes (should be empty) ==="
  docker ps --format '{{.Names}} {{.Ports}}' 2>/dev/null | grep -vE '127\.0\.0\.1|::1' || echo "(none — good)"
} | tee "$OUT/listen.txt"

{
  echo "=== loopback health ==="
  if [[ -x /usr/bin/atlas-health ]]; then
    /usr/bin/atlas-health
  else
    for u in \
      http://127.0.0.1:8080/ \
      http://127.0.0.1:6333/readyz \
      http://127.0.0.1:8090/ \
      http://127.0.0.1:11434/api/tags
    do
      code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 2 "$u" || echo 000)
      echo "$code  $u"
    done
  fi
} | tee "$OUT/health.txt"

{
  echo "=== install desktop icons (should be absent) ==="
  ls /home/*/Desktop/install-atlas-os.desktop 2>/dev/null || echo "(none — good)"
  ls /home/*/Desktop/calamares-install-debian.desktop 2>/dev/null || echo "(none — good)"
} | tee "$OUT/desktop-icons.txt"

echo "Evidence written to $OUT"
