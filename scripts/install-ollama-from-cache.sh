#!/usr/bin/env bash
# Install host-native Ollama from verified cache archive.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="${1:-$ROOT/build-cache/ollama}"
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
install -d /usr/bin
install -m 755 "$TMP/bin/ollama" /usr/bin/ollama || install -m 755 "$TMP/ollama" /usr/bin/ollama
mkdir -p /srv/atlas/models/ollama
systemctl enable ollama.service || true
echo "Ollama installed."
