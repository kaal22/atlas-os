#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/dist}"
mkdir -p "$OUT"
VERSION="$(cat "$ROOT/VERSION")"
python3 - <<PY
import json, pathlib, datetime
out = pathlib.Path(r"$OUT") / f"atlas-os-$VERSION-sbom.spdx.json"
doc = {
  "spdxVersion": "SPDX-2.3",
  "dataLicense": "CC0-1.0",
  "SPDXID": "SPDXRef-DOCUMENT",
  "name": f"atlas-os-$VERSION",
  "creationInfo": {
    "created": datetime.datetime.utcnow().isoformat() + "Z",
    "creators": ["Tool: atlas-generate-sbom"]
  },
  "packages": [
    {"name": "atlas-os", "SPDXID": "SPDXRef-atlas-os", "versionInfo": "$VERSION", "downloadLocation": "NOASSERTION"},
    {"name": "project-nomad", "SPDXID": "SPDXRef-nomad", "versionInfo": "v1.33.0", "licenseConcluded": "Apache-2.0"},
  ]
}
out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
print("Wrote", out)
PY
