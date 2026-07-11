#!/bin/bash
# Atlas first-boot: generate unique secrets, never reuse ISO defaults.
set -euo pipefail

FLAG=/etc/atlas/firstboot-pending
DONE=/etc/atlas/firstboot-done
DATA=/srv/atlas
SECRETS=/etc/atlas/secrets

if [[ -f "$DONE" ]]; then
  exit 0
fi

mkdir -p "$DATA"/{users,workspaces,documents,knowledge,embeddings,models/ollama,maps,kiwix,kolibri,media,content-packs,agent-packages,backups,exports,databases,logs}
mkdir -p "$SECRETS"
chmod 700 "$SECRETS"

if [[ ! -f "$SECRETS/device-id" ]]; then
  if command -v openssl >/dev/null; then
    openssl rand -hex 16 > "$SECRETS/device-id"
  else
    head -c 16 /dev/urandom | xxd -p > "$SECRETS/device-id"
  fi
fi

if [[ ! -f "$SECRETS/mysql-root" ]]; then
  openssl rand -base64 32 | tr -d '\n' > "$SECRETS/mysql-root"
fi

if [[ ! -f "$SECRETS/redis" ]]; then
  openssl rand -base64 32 | tr -d '\n' > "$SECRETS/redis"
fi

chmod 600 "$SECRETS"/*

# Import offline OCI payload if present (Phase 2+)
if [[ -x /usr/lib/atlas/import-payload.sh ]]; then
  /usr/lib/atlas/import-payload.sh || true
fi

rm -f "$FLAG"
date -u +%Y-%m-%dT%H:%M:%SZ > "$DONE"
echo "Atlas first-boot completed."
