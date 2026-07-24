#!/bin/bash
# Enable Atlas nginx site on loopback only; disable generic default that listens *:80.
set -euo pipefail

AVAIL=/etc/nginx/sites-available/atlas-command-centre
ENABLED=/etc/nginx/sites-enabled/atlas-command-centre

if [[ ! -f "$AVAIL" ]]; then
  echo "atlas-proxy: site config missing at $AVAIL" >&2
  exit 1
fi

mkdir -p /etc/nginx/sites-enabled
ln -sfn "$AVAIL" "$ENABLED"

# Drop stock default site if present (often listens on 0.0.0.0:80).
rm -f /etc/nginx/sites-enabled/default

# Prefer nginx packaged unit
if command -v nginx >/dev/null; then
  nginx -t
  systemctl enable nginx.service >/dev/null 2>&1 || true
  systemctl restart nginx.service || systemctl start nginx.service || true
fi

echo "atlas-proxy: optional loopback compat enabled (127.0.0.1:80 -> 127.0.0.1:8787); canonical CC is :8787"
