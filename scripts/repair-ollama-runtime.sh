#!/usr/bin/env bash
# Repair a VM/ISO install that has /usr/bin/ollama but missing llama-server.
# Usage (on the Atlas VM after curling the tarball from the build host):
#   sudo ./scripts/repair-ollama-runtime.sh /tmp/ollama-runtime-cpu.tar.zst
set -euo pipefail
ARCHIVE="${1:-}"
if [[ -z "$ARCHIVE" || ! -f "$ARCHIVE" ]]; then
  echo "Usage: $0 /path/to/ollama-runtime-cpu.tar.zst" >&2
  exit 1
fi
if [[ "$(id -u)" -ne 0 ]]; then
  echo "Re-executing with sudo..."
  exec sudo -E "$0" "$@"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
if [[ "$ARCHIVE" == *.zst ]]; then
  zstd -d -c "$ARCHIVE" | tar -x -C "$TMP"
else
  tar -xf "$ARCHIVE" -C "$TMP"
fi

install -d /usr/bin /usr/lib/ollama
if [[ -f "$TMP/usr/bin/ollama" ]]; then
  install -m 755 "$TMP/usr/bin/ollama" /usr/bin/ollama
fi
if [[ -d "$TMP/usr/lib/ollama" ]]; then
  cp -a "$TMP/usr/lib/ollama/." /usr/lib/ollama/
fi

if [[ ! -x /usr/lib/ollama/llama-server ]]; then
  echo "ERROR: llama-server still missing after extract" >&2
  ls -la /usr/lib/ollama >&2 || true
  exit 1
fi

systemctl restart ollama.service || systemctl start ollama.service
sleep 1
curl -fsS http://127.0.0.1:11434/api/tags >/dev/null
echo "OK: Ollama runtime repaired (llama-server present, API responding)"
