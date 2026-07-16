#!/usr/bin/env bash
# Hot-fix NOMAD when other Phase 2 services are green but Nomad is down.
# Usually Redis protected-mode, wrong port mapping, or MySQL secret/volume mismatch.
# Run on the installed system:
#   sudo bash repair-nomad-redis.sh
# Wipe MySQL data dir if healthcheck auth fails (secrets rotated after first init):
#   sudo ATLAS_WIPE_MYSQL=1 bash repair-nomad-redis.sh
set -euo pipefail
COMPOSE="${1:-/srv/atlas/compose/atlas-core.yml}"
ENV_FILE="/srv/atlas/compose/.env"
WIPE_MYSQL="${ATLAS_WIPE_MYSQL:-0}"

[[ -f "$COMPOSE" ]] || { echo "missing $COMPOSE" >&2; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "missing $ENV_FILE — run firstboot/import first" >&2; exit 1; }

# Prefer scp'd fixed compose, then package copy.
for cand in /tmp/atlas-core.yml /usr/share/atlas/compose/atlas-core.yml; do
  if [[ -f "$cand" ]]; then
    cp -f "$cand" "$COMPOSE"
    break
  fi
done

compose() {
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE" "$@"
}

if [[ "$WIPE_MYSQL" == "1" ]]; then
  echo "Wiping MySQL volume (ATLAS_WIPE_MYSQL=1)..."
  compose stop mysql atlas-nomad-core 2>/dev/null || true
  compose rm -f mysql atlas-nomad-core 2>/dev/null || true
  rm -rf /srv/atlas/databases/mysql
  mkdir -p /srv/atlas/databases/mysql
  compose up -d mysql
  echo "Waiting for mysql to accept connections (not blocked on healthy for NOMAD)..."
  sleep 15
fi

compose up -d redis mysql
sleep 2
compose up -d --force-recreate atlas-nomad-core
echo "Waiting for NOMAD..."
for i in $(seq 1 90); do
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:8090/api/health || echo 000)
  if [[ "$code" != "000" && "$code" != "000000" ]]; then
    echo "NOMAD ready: HTTP $code"
    compose ps
    exit 0
  fi
  sleep 2
done
echo "Still down — recent logs:" >&2
compose logs --tail=80 atlas-nomad-core mysql redis >&2 || true
echo "If mysql is unhealthy, try: sudo ATLAS_WIPE_MYSQL=1 bash $0" >&2
exit 1
