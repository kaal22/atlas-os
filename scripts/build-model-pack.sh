#!/usr/bin/env bash
# Create starter model pack metadata (actual weights pulled on lock-refresh host).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist/packs"
mkdir -p "$OUT/staging/payload" "$OUT/staging/licences" "$OUT/staging/attribution"
cat > "$OUT/staging/manifest.json" <<'EOF'
{
  "schema": "atlas.pack/v1",
  "id": "atlas.models.starter",
  "version": "0.1.0",
  "type": "atlas.content.model",
  "name": "Starter Models",
  "description": "qwen3:4b and nomic-embed-text:v1.5 packaged for offline import.",
  "size_bytes": 0,
  "minimum_os_version": "0.1.0",
  "architectures": ["amd64"],
  "mount_target": "/srv/atlas/models/ollama",
  "licences": ["Apache-2.0"],
  "sources": ["ollama:qwen3:4b", "ollama:nomic-embed-text:v1.5"],
  "dependencies": [],
  "conflicts": [],
  "digest": "sha256:0000000000000000000000000000000000000000000000000000000000000000"
}
EOF
echo "Models are pulled via scripts on a networked builder; see product §52.7." > "$OUT/staging/payload/README.txt"
export ATLAS_ALLOW_UNSIGNED=1
python3 "$ROOT/packages/atlas-content-manager/usr/lib/atlas/content_manager.py" >/dev/null || true
# Use content manager build_pack via small python
python3 - <<PY
import json, os, sys
from pathlib import Path
sys.path.insert(0, r"$ROOT/packages/atlas-content-manager/usr/lib/atlas")
from content_manager import build_pack, sha256_file
stage = Path(r"$OUT/staging")
out = Path(r"$OUT") / "atlas-models-starter.atlas-pack"
os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
digest = build_pack(stage, out)
m = json.loads((stage / "manifest.json").read_text())
m["digest"] = digest if digest.startswith("sha256:") else digest
# digest from sha256_file already prefixed
m["digest"] = digest
(stage / "manifest.json").write_text(json.dumps(m, indent=2))
build_pack(stage, out)
print("Wrote", out, digest)
PY
