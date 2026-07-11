#!/usr/bin/env bash
# Validate sources.catalog.yaml structure (Phase 0).
set -euo pipefail

CATALOG="${1:?usage: validate-catalog.sh <sources.catalog.yaml>}"

if [[ ! -f "$CATALOG" ]]; then
  echo "ERROR: catalogue not found: $CATALOG" >&2
  exit 1
fi

python3 - "$CATALOG" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
required = [
    "schema:",
    "project_nomad:",
    "core_images:",
    "standard_apps:",
    "ollama:",
    "models:",
    "debian:",
    "iso_profiles:",
]
missing = [r for r in required if r not in text]
if missing:
    print("ERROR: catalogue missing keys:", ", ".join(missing), file=sys.stderr)
    sys.exit(1)

# Require top-level ollama: mapping (not image refs like ollama/ollama:tag)
import re
m = re.search(r"(?m)^ollama:\s*$", text)
if not m:
    print("ERROR: top-level ollama: key missing", file=sys.stderr)
    sys.exit(1)
rest = text[m.end():]
lines = []
for line in rest.splitlines():
    if line and not line.startswith(" ") and not line.startswith("\t") and re.match(r"^[A-Za-z0-9_]+:\s*$", line):
        break
    lines.append(line)
block = "\n".join(lines)
if not re.search(r"(?m)^\s+version:\s*\S+", block):
    print("ERROR: ollama.version missing", file=sys.stderr)
    sys.exit(1)

print(f"OK: catalogue validated: {path}")
PY
