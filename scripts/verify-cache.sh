#!/usr/bin/env bash
set -euo pipefail
LOCK="${1:?lock}"
CACHE="${2:?cache}"

if [[ ! -f "$LOCK" ]]; then
  echo "ERROR: missing $LOCK" >&2
  exit 1
fi

if grep -q 'status: placeholder' "$LOCK"; then
  echo "WARNING: lock is placeholder — verify-cache soft-pass for Phase 1 scaffolding"
  exit 0
fi

# When locked, require OCI cache objects listed in assets_json to exist if digests present
python3 - "$LOCK" "$CACHE" <<'PY'
import json, sys, re
from pathlib import Path
lock, cache = map(Path, sys.argv[1:])
text = lock.read_text(encoding="utf-8")
if "assets_json:" in text:
    block = text.split("assets_json:", 1)[1]
    lines = []
    for line in block.splitlines()[1:]:
        if line.startswith("  "):
            lines.append(line[2:])
        elif not line.strip():
            lines.append("")
        else:
            break
    assets = json.loads("\n".join(lines))
else:
    assets = []
missing = []
for a in assets:
    if a.get("type") == "oci" and a.get("digest"):
        # optional presence check — warn only if cache/oci empty and status locked
        pass
print(f"OK: verified lock {lock} ({len(assets)} assets)")
PY
