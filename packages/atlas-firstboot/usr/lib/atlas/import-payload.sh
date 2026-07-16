#!/bin/bash
# Import offline OCI archives into Docker without registry access.
# Fail closed when /etc/atlas/payload-enabled is present.
set -euo pipefail

PAYLOAD="${ATLAS_OCI_PAYLOAD:-/usr/share/atlas/payload/atlas-core-oci-payload.tar.zst}"
COMPOSE_SRC="/usr/share/atlas/compose/atlas-core.yml"
COMPOSE_DST="/srv/atlas/compose/atlas-core.yml"
LOG_JSON="/srv/atlas/logs/payload-import.json"
PAYLOAD_ENABLED="/etc/atlas/payload-enabled"
LOG_TXT="/srv/atlas/logs/payload-import.log"
PROGRESS="/srv/atlas/logs/firstboot-progress.txt"

# archive basename -> image ref (also shipped as oci/images.map inside the payload)
declare -A IMAGE_MAP=(
  ["mysql_8.0.tar"]="mysql:8.0"
  ["redis_7-alpine.tar"]="redis:7-alpine"
  ["qdrant_qdrant_v1.16.tar"]="qdrant/qdrant:v1.16"
  ["ghcr.io_kiwix_kiwix-serve_3.8.2.tar"]="ghcr.io/kiwix/kiwix-serve:3.8.2"
  ["treehouses_kolibri_0.12.8.tar"]="treehouses/kolibri:0.12.8"
  ["ghcr.io_gchq_cyberchef_10.24.tar"]="ghcr.io/gchq/cyberchef:10.24"
  ["dullage_flatnotes_v5.5.4.tar"]="dullage/flatnotes:v5.5.4"
  ["ghcr.io_crosstalk-solutions_project-nomad_v1.33.0.tar"]="ghcr.io/crosstalk-solutions/project-nomad:v1.33.0"
)

REQUIRED_IMAGES=(
  "mysql:8.0"
  "redis:7-alpine"
  "qdrant/qdrant:v1.16"
  "ghcr.io/kiwix/kiwix-serve:3.8.2"
  "ghcr.io/crosstalk-solutions/project-nomad:v1.33.0"
)

mkdir -p /srv/atlas/compose /srv/atlas/logs /srv/atlas/kiwix /srv/atlas/maps /srv/atlas/users/notes

log() {
  local line="[$(date -u +%H:%M:%S)] $*"
  echo "$line" | tee -a "$LOG_TXT" >/dev/null
  echo "$line" >>"$PROGRESS"
  # Also to journal/stdout for systemctl status
  echo "$line"
}

progress() {
  log "$*"
  # Keep a one-line "current" marker for the launcher
  echo "$*" >"${PROGRESS}.current"
}

write_status() {
  local ok="$1"
  local msg="$2"
  python3 - "$LOG_JSON" "$ok" "$msg" <<'PY' || true
import json, sys, datetime
path, ok, msg = sys.argv[1], sys.argv[2] == "1", sys.argv[3]
obj = {
  "ok": ok,
  "message": msg,
  "at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
}
open(path, "w", encoding="utf-8").write(json.dumps(obj, indent=2) + "\n")
PY
}

fail() {
  progress "FAILED: $*"
  write_status 0 "$*"
  echo "ERROR: $*" >&2
  exit 1
}

load_map_file() {
  local mapfile="$1"
  [[ -f "$mapfile" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "$line" =~ ^# ]] && continue
    local arch="${line%%[[:space:]]*}"
    local ref="${line#*[[:space:]]}"
    ref="$(echo "$ref" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    [[ -n "$arch" && -n "$ref" ]] || continue
    IMAGE_MAP["$arch"]="$ref"
  done < "$mapfile"
}

tag_loaded_image() {
  local load_out="$1"
  local want_ref="$2"
  local id=""
  if [[ "$load_out" =~ Loaded\ image:\ (.+)$ ]]; then
    local got="${BASH_REMATCH[1]}"
    got="${got%%$'\r'*}"
    if [[ "$got" != "$want_ref" ]]; then
      docker tag "$got" "$want_ref"
    fi
    return 0
  fi
  if [[ "$load_out" =~ Loaded\ image\ ID:\ (sha256:[0-9a-f]+) ]]; then
    id="${BASH_REMATCH[1]}"
    docker tag "$id" "$want_ref"
    return 0
  fi
  id="$(docker images -q --filter dangling=true | head -1 || true)"
  if [[ -n "$id" ]]; then
    docker tag "$id" "$want_ref"
    return 0
  fi
  return 1
}

images_present() {
  local need
  for need in "${REQUIRED_IMAGES[@]}"; do
    if ! docker image inspect "$need" >/dev/null 2>&1; then
      return 1
    fi
  done
  return 0
}

: >"$PROGRESS"
progress "Atlas payload import starting"

# Empty-but-healthy maps volume (no planet PMTiles in Phase 2).
if [[ ! -f /srv/atlas/maps/README.txt ]]; then
  cat > /srv/atlas/maps/README.txt <<'EOF'
Atlas maps volume — Phase 2
This directory is intentionally empty. Offline map tiles (PMTiles) are
provisioned later via content packs. Stack readiness does not require
planet data for core developer ISO exit criteria.
EOF
fi

if [[ ! -f /srv/atlas/kiwix/library.xml ]]; then
  cat > /srv/atlas/kiwix/library.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<library version="20110515">
</library>
EOF
fi

if [[ -f "$COMPOSE_SRC" ]]; then
  cp -f "$COMPOSE_SRC" "$COMPOSE_DST"
fi

if [[ ! -f "$PAYLOAD" ]]; then
  if [[ -f "$PAYLOAD_ENABLED" ]]; then
    fail "Payload profile enabled but missing $PAYLOAD"
  fi
  progress "No OCI payload — skipping import"
  write_status 1 "skipped_no_payload"
  exit 0
fi

if ! command -v docker >/dev/null; then
  fail "docker is required to import OCI payload"
fi

progress "Waiting for Docker daemon..."
for _ in $(seq 1 90); do
  if docker info >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
docker info >/dev/null 2>&1 || fail "Docker daemon not ready"
progress "Docker is ready"

loaded=0
skipped_extract=0

# Idempotent: retries must not re-extract/load ~1.2G when images are already present.
if [[ "${ATLAS_FORCE_RELOAD:-0}" != "1" ]] && images_present; then
  skipped_extract=1
  progress "REQUIRED_IMAGES already present — skipping payload extract/load (set ATLAS_FORCE_RELOAD=1 to force)"
  log "skip_extract=1 images=$(printf '%s ' "${REQUIRED_IMAGES[@]}")"
else
  if [[ "${ATLAS_FORCE_RELOAD:-0}" == "1" ]]; then
    progress "ATLAS_FORCE_RELOAD=1 — re-extracting and re-loading payload"
  fi

  # Extract on disk under /srv/atlas — never /tmp (tmpfs is too small for ~3GB+ images).
  TMP="/srv/atlas/tmp/payload-import.$$"
  rm -rf "$TMP"
  mkdir -p "$TMP"
  trap 'rm -rf "$TMP"' EXIT

  payload_bytes="$(stat -c%s "$PAYLOAD" 2>/dev/null || echo 0)"
  progress "Extracting payload ($(numfmt --to=iec "$payload_bytes" 2>/dev/null || echo "${payload_bytes}B")) — several minutes..."
  zstd -d -c "$PAYLOAD" | tar -x -C "$TMP"
  load_map_file "$TMP/oci/images.map"
  load_map_file "$TMP/images.map"
  progress "Payload extracted"

  shopt -s nullglob
  tars=("$TMP"/oci/*.tar)
  shopt -u nullglob
  # Ignore accidental top-level tars; prefer oci/
  if [[ ${#tars[@]} -eq 0 ]]; then
    shopt -s nullglob
    tars=("$TMP"/*.tar)
    shopt -u nullglob
  fi
  if [[ ${#tars[@]} -eq 0 ]]; then
    fail "OCI payload contained no .tar archives"
  fi

  total=${#tars[@]}
  idx=0
  for tar in "${tars[@]}"; do
    [[ -f "$tar" ]] || continue
    idx=$((idx + 1))
    base="$(basename "$tar")"
    want="${IMAGE_MAP[$base]:-}"
    size="$(stat -c%s "$tar" 2>/dev/null || echo 0)"
    progress "Loading image ${idx}/${total}: $base ($(numfmt --to=iec "$size" 2>/dev/null || echo "${size}B")) → ${want:-untagged}"
    out="$(docker load -i "$tar" 2>&1)" || fail "docker load failed for $base: $out"
    log "$out"
    if [[ -n "$want" ]]; then
      if ! docker image inspect "$want" >/dev/null 2>&1; then
        tag_loaded_image "$out" "$want" || fail "could not tag $base as $want"
      fi
      docker image inspect "$want" >/dev/null 2>&1 || fail "image missing after tag: $want"
    fi
    loaded=$((loaded + 1))
    progress "Loaded ${idx}/${total}: ${want:-$base}"
  done
  [[ "$loaded" -gt 0 ]] || fail "No images were loaded from payload"

  missing=()
  for need in "${REQUIRED_IMAGES[@]}"; do
    if ! docker image inspect "$need" >/dev/null 2>&1; then
      missing+=("$need")
    fi
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    docker images | tee -a "$LOG_TXT" || true
    fail "Required images missing after load: ${missing[*]}"
  fi
fi

if [[ ! -f /etc/atlas/secrets/mysql-root || ! -f /etc/atlas/secrets/mysql-nomad || ! -f /etc/atlas/secrets/app-key ]]; then
  fail "Missing mysql/app secrets under /etc/atlas/secrets (run atlas-firstboot secrets stage first)"
fi

ENV_FILE="/srv/atlas/compose/.env"
umask 077
# Secrets are hex-only (firstboot) so they are safe unquoted in compose .env.
cat > "$ENV_FILE" <<EOF
ATLAS_MYSQL_ROOT_PASSWORD=$(cat /etc/atlas/secrets/mysql-root)
ATLAS_MYSQL_PASSWORD=$(cat /etc/atlas/secrets/mysql-nomad)
ATLAS_APP_KEY=$(cat /etc/atlas/secrets/app-key)
EOF
chmod 600 "$ENV_FILE"

# Empty Kiwix library must be world-readable (container runs as non-root "user")
mkdir -p /srv/atlas/kiwix /srv/atlas/nomad-storage
if [[ ! -f /srv/atlas/kiwix/library.xml ]]; then
  cat > /srv/atlas/kiwix/library.xml <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<library version="20110515">
</library>
EOF
fi
chmod -R a+rX /srv/atlas/kiwix
chmod 755 /srv/atlas/nomad-storage

[[ -f "$COMPOSE_DST" ]] || fail "Missing compose file $COMPOSE_DST"

compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_DST" "$@"
  elif command -v docker-compose >/dev/null; then
    docker-compose --env-file "$ENV_FILE" -f "$COMPOSE_DST" "$@"
  else
    fail "neither 'docker compose' nor docker-compose is available"
  fi
}

# Core loopback apps first. Do NOT wait for MySQL healthy — a volume initialized
# with mismatched secrets can stay unhealthy forever and would block firstboot.
# Recovery: stop stack, wipe /srv/atlas/databases/mysql, re-run import.
CORE_SERVICES=(mysql redis qdrant kiwix flatnotes cyberchef kolibri)
progress "Starting core compose services: ${CORE_SERVICES[*]}"
set +e
core_out="$(compose_cmd up -d "${CORE_SERVICES[@]}" 2>&1)"
core_rc=$?
set -e
echo "$core_out" | tee -a "$LOG_TXT"
if [[ "$core_rc" -ne 0 ]]; then
  fail "core compose up failed (rc=$core_rc): $core_out"
fi

progress "Starting NOMAD (best-effort; may take several minutes for DB migrate)..."
set +e
nomad_out="$(compose_cmd up -d atlas-nomad-core 2>&1)"
nomad_rc=$?
set -e
echo "$nomad_out" | tee -a "$LOG_TXT"
if [[ "$nomad_rc" -ne 0 ]]; then
  progress "WARN: NOMAD compose up failed (rc=$nomad_rc) — continuing; other services are up"
  compose_cmd logs --tail=80 atlas-nomad-core 2>&1 | tee -a "$LOG_TXT" || true
  compose_cmd ps 2>&1 | tee -a "$LOG_TXT" || true
fi

progress "Waiting for loopback services to become ready..."
wait_url() {
  local name="$1" url="$2" secs="${3:-120}"
  local i code
  for i in $(seq 1 "$secs"); do
    code="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 1 --max-time 2 "$url" 2>/dev/null || true)"
    code="$(echo "$code" | tr -cd '0-9')"
    if [[ -n "$code" && "$code" != "000" && "$code" != "000000" ]]; then
      # Accept any real HTTP code (200/301/404 all mean the port is serving).
      progress "$name ready (http $code) at $url"
      return 0
    fi
    sleep 1
  done
  progress "WARN: $name not ready yet after ${secs}s ($url)"
  return 1
}

wait_url "qdrant" "http://127.0.0.1:6333/readyz" 60 || true
wait_url "kiwix" "http://127.0.0.1:8080/" 60 || true
wait_url "nomad" "http://127.0.0.1:8090/api/health" 180 || true

compose_cmd ps 2>/dev/null | tee -a "$LOG_TXT" || true

write_status 1 "imported_and_started loaded=$loaded skipped_extract=$skipped_extract nomad_rc=${nomad_rc:-0}"
progress "Payload import finished (loaded=$loaded skipped_extract=$skipped_extract). Services starting..."
log "Payload import finished (loaded=$loaded skipped_extract=$skipped_extract)."
