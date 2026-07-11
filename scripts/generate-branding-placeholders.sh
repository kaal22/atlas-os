#!/usr/bin/env bash
# Prefer the glowing-triangle master art when available; else tiny placeholders.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if python3 -c 'from PIL import Image' 2>/dev/null; then
  if [[ -f "$ROOT/scripts/apply-triangle-branding.py" ]]; then
    python3 "$ROOT/scripts/apply-triangle-branding.py" && exit 0
  fi
fi

# Fallback 1x1 placeholders
python3 - <<'PY'
import struct, zlib, pathlib, sys
root = pathlib.Path(r'''ROOT'''.replace('ROOT', sys.argv[1] if False else ''))
PY
BRAND="$ROOT/calamares/branding/atlas"
PIX="$ROOT/config/includes.chroot/usr/share/pixmaps"
SHARE="$ROOT/config/includes.chroot/usr/share/atlas/branding"
mkdir -p "$BRAND" "$PIX" "$SHARE"
python3 - "$BRAND" "$PIX" "$SHARE" <<'PY'
import struct, zlib, pathlib, sys

def write_png(path, rgb=(0, 0, 0)):
    r, g, b = rgb
    raw = bytes([0, r, g, b])
    compressed = zlib.compress(raw, 9)
    def chunk(tag, data):
        return struct.pack('>I', len(data)) + tag + data + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff)
    ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
    data = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr) + chunk(b'IDAT', compressed) + chunk(b'IEND', b'')
    pathlib.Path(path).write_bytes(data)

brand, pix, share = map(pathlib.Path, sys.argv[1:])
for name in ('logo.png', 'welcome.png', 'banner.png', 'productIcon.png'):
    write_png(brand / name)
write_png(pix / 'atlas.png')
write_png(share / 'logo.png')
print('Fallback placeholders written (install Pillow + triangle art for real branding)')
PY
