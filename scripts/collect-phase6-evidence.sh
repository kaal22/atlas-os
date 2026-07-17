#!/usr/bin/env bash
# Collect Phase 6 content-pack evidence on an installed Atlas OS system.
set -euo pipefail

OUT="${1:-/srv/atlas/logs/phase6-evidence.txt}"
mkdir -p "$(dirname "$OUT")"
{
  echo "=== Phase 6 evidence $(date -Is) ==="
  echo
  echo "-- catalogue --"
  ls -la /usr/share/atlas/catalogue.json 2>/dev/null || echo "catalogue_missing"
  echo
  echo "-- bundled packs --"
  ls -la /usr/share/atlas/packs/ 2>/dev/null || echo "packs_dir_missing"
  echo
  echo "-- installed registry --"
  cat /srv/atlas/content-packs/installed.json 2>/dev/null || echo "installed_json_missing"
  echo
  echo "-- maps mount --"
  ls -la /srv/atlas/maps/uk 2>/dev/null || echo "maps_not_installed"
  echo
  echo "-- content API (401 without session is OK) --"
  curl -sS -o /dev/null -w "content_catalogue_http=%{http_code}\n" --max-time 3 \
    http://127.0.0.1/api/content/catalogue || true
  echo
  echo "Manual: login as owner → Content → preview stub pack → install → verify /srv/atlas/maps/uk"
  echo "Manual: uninstall pack → entry removed from installed.json"
} | tee "$OUT"

echo "Wrote $OUT"
