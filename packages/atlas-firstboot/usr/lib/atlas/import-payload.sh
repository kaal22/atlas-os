#!/bin/bash
# Import offline OCI archives into Docker without registry access.
set -euo pipefail

PAYLOAD="${ATLAS_OCI_PAYLOAD:-/usr/share/atlas/payload/atlas-core-oci-payload.tar.zst}"
COMPOSE_SRC="/usr/share/atlas/compose/atlas-core.yml"
COMPOSE_DST="/srv/atlas/compose/atlas-core.yml"

mkdir -p /srv/atlas/compose /srv/atlas/logs

if [[ -f "$COMPOSE_SRC" ]]; then
  cp "$COMPOSE_SRC" "$COMPOSE_DST"
fi

if [[ ! -f "$PAYLOAD" ]]; then
  echo "No OCI payload at $PAYLOAD — skipping import (expected on core ISO without payload)."
  exit 0
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
zstd -d -c "$PAYLOAD" | tar -x -C "$TMP"

if command -v docker >/dev/null; then
  for tar in "$TMP"/*.tar "$TMP"/oci/*.tar; do
    [[ -f "$tar" ]] || continue
    docker load -i "$tar" || true
  done
  if [[ -f /etc/atlas/secrets/redis ]]; then
    export ATLAS_REDIS_PASSWORD="$(cat /etc/atlas/secrets/redis)"
  fi
  if [[ -f "$COMPOSE_DST" ]]; then
    docker compose -f "$COMPOSE_DST" up -d || true
  fi
fi

echo "Payload import finished."
