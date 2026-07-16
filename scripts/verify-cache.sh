#!/usr/bin/env bash
# Verify build-cache against sources.lock.yaml
set -euo pipefail
LOCK="${1:?lock}"
CACHE="${2:?cache}"

if [[ ! -f "$LOCK" ]]; then
  echo "ERROR: missing $LOCK" >&2
  exit 1
fi

if grep -q 'status: placeholder' "$LOCK"; then
  echo "WARNING: lock is placeholder — verify-cache soft-pass (run make lock-refresh)"
  exit 0
fi

python3 - "$LOCK" "$CACHE" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

lock, cache = map(Path, sys.argv[1:])
text = lock.read_text(encoding="utf-8")
if "assets_json:" not in text:
    print("ERROR: lock missing assets_json", file=sys.stderr)
    sys.exit(1)

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

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

errors = []
for a in assets:
    rel = a.get("archive") or a.get("path")
    if not rel:
        continue
    path = cache / rel
    if not path.exists():
        errors.append(f"missing {rel}")
        continue
    expected = a.get("archive_sha256") or (a.get("sha256") if a.get("type") == "file" else None)
    if expected:
        got = sha256(path)
        if got.lower() != expected.lower():
            errors.append(f"hash mismatch {rel}: got {got} want {expected}")

if errors:
    print("ERROR: verify-cache failed:", file=sys.stderr)
    for e in errors:
        print(f"  {e}", file=sys.stderr)
    sys.exit(1)

print(f"OK: verified lock {lock} ({len(assets)} assets)")
PY
