#!/usr/bin/env bash
# Collect Phase 7 backup/update evidence on an installed Atlas OS system.
set -euo pipefail

OUT="${1:-/srv/atlas/logs/phase7-evidence.txt}"
mkdir -p "$(dirname "$OUT")"
{
  echo "=== Phase 7 evidence $(date -Is) ==="
  echo
  echo "-- backup module --"
  python3 -c "import backup_service; print('backup_service', backup_service.FORMAT_VERSION)" 2>/dev/null \
    || ls -la /usr/lib/atlas/backup_service.py 2>/dev/null || echo "backup_service_missing"
  echo
  echo "-- updater module --"
  python3 -c "import updater; print('updater ok')" 2>/dev/null \
    || ls -la /usr/lib/atlas/updater.py 2>/dev/null || echo "updater_missing"
  echo
  echo "-- bundled updates --"
  ls -la /usr/share/atlas/updates/ 2>/dev/null || echo "updates_dir_missing"
  echo
  echo "-- full backups --"
  ls -la /srv/atlas/backups/full/ 2>/dev/null || echo "no_full_backups_yet"
  echo
  echo "-- update diagnostics --"
  ls -la /srv/atlas/logs/update-*.json 2>/dev/null || echo "no_update_logs_yet"
  echo
  echo "-- snapshots --"
  ls -la /srv/atlas/snapshots/ 2>/dev/null || echo "no_snapshots_yet"
  echo
  echo "-- APIs (401 without session is OK) --"
  curl -sS -o /dev/null -w "backup_list_http=%{http_code}\n" --max-time 3 \
    http://127.0.0.1/api/backup/list || true
  curl -sS -o /dev/null -w "updates_browse_http=%{http_code}\n" --max-time 3 \
    http://127.0.0.1/api/updates/browse || true
  echo
  echo "Manual: System → create encrypted backup → verify."
  echo "Manual: System → apply broken rollback bundle → expect auto-rollback + update-*.json log."
} | tee "$OUT"

echo "Wrote $OUT"
