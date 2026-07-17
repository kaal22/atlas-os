#!/usr/bin/env bash
# Install host-native Ollama from verified cache archive into DEST (default /).
# Modern Ollama needs both bin/ollama and lib/ollama/llama-server (+ CPU libs).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="${1:-$ROOT/build-cache/ollama}"
DEST="${2:-/}"
ARCHIVE="$CACHE/ollama-linux-amd64-0.31.2.tar.zst"
EXPECTED_SHA="2c88f0f31a959bac5a3cad4cc5296ec568551d4aa79f548f554adb2b575b3133"
# CUDA blobs are ~2GB — skip for CPU-first ISOs unless explicitly requested.
WITH_CUDA="${ATLAS_OLLAMA_WITH_CUDA:-0}"

if [[ ! -f "$ARCHIVE" ]]; then
  echo "Ollama archive missing: $ARCHIVE" >&2
  echo "Download during lock-refresh into build-cache/ollama/" >&2
  exit 1
fi

echo "$EXPECTED_SHA  $ARCHIVE" | sha256sum -c -
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
zstd -d -c "$ARCHIVE" | tar -x -C "$TMP"

install -d "$DEST/usr/bin" "$DEST/usr/lib/ollama"
if [[ -f "$TMP/bin/ollama" ]]; then
  install -m 755 "$TMP/bin/ollama" "$DEST/usr/bin/ollama"
elif [[ -f "$TMP/ollama" ]]; then
  install -m 755 "$TMP/ollama" "$DEST/usr/bin/ollama"
else
  echo "ERROR: ollama binary not found in archive" >&2
  exit 1
fi

if [[ ! -d "$TMP/lib/ollama" ]]; then
  echo "ERROR: lib/ollama missing from archive (need llama-server)" >&2
  exit 1
fi

# Copy runtime libs; optionally omit CUDA packs to keep the live image lean.
if [[ "$WITH_CUDA" == "1" ]]; then
  cp -a "$TMP/lib/ollama/." "$DEST/usr/lib/ollama/"
else
  # rsync preferred; fall back to find/cp
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --exclude 'cuda_v12/' --exclude 'cuda_v13/' \
      "$TMP/lib/ollama/" "$DEST/usr/lib/ollama/"
  else
    find "$TMP/lib/ollama" -mindepth 1 -maxdepth 1 ! -name 'cuda_v12' ! -name 'cuda_v13' \
      -exec cp -a {} "$DEST/usr/lib/ollama/" \;
  fi
fi

if [[ ! -x "$DEST/usr/lib/ollama/llama-server" ]]; then
  echo "ERROR: llama-server not installed at $DEST/usr/lib/ollama/llama-server" >&2
  exit 1
fi

install -d "$DEST/srv/atlas/models/ollama"
if [[ "$DEST" == "/" ]] && command -v systemctl >/dev/null; then
  systemctl enable ollama.service || true
fi
echo "Ollama installed into $DEST (llama-server ok; cuda=$([[ $WITH_CUDA == 1 ]] && echo yes || echo skipped))"
