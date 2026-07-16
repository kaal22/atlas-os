#!/usr/bin/env bash
# Install host-native Ollama from verified cache archive into DEST (default /).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="${1:-$ROOT/build-cache/ollama}"
DEST="${2:-/}"
ARCHIVE="$CACHE/ollama-linux-amd64-0.31.2.tar.zst"
EXPECTED_SHA="2c88f0f31a959bac5a3cad4cc5296ec568551d4aa79f548f554adb2b575b3133"

if [[ ! -f "$ARCHIVE" ]]; then
  echo "Ollama archive missing: $ARCHIVE" >&2
  echo "Download during lock-refresh into build-cache/ollama/" >&2
  exit 1
fi

echo "$EXPECTED_SHA  $ARCHIVE" | sha256sum -c -
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
zstd -d -c "$ARCHIVE" | tar -x -C "$TMP"

install -d "$DEST/usr/bin"
if [[ -f "$TMP/bin/ollama" ]]; then
  install -m 755 "$TMP/bin/ollama" "$DEST/usr/bin/ollama"
elif [[ -f "$TMP/ollama" ]]; then
  install -m 755 "$TMP/ollama" "$DEST/usr/bin/ollama"
else
  echo "ERROR: ollama binary not found in archive" >&2
  exit 1
fi

install -d "$DEST/srv/atlas/models/ollama"
if [[ "$DEST" == "/" ]] && command -v systemctl >/dev/null; then
  systemctl enable ollama.service || true
fi
echo "Ollama installed into $DEST"
