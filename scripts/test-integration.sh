#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "== Atlas integration tests =="
python3 "$ROOT/tests/integration/test_compose_schema.py"
python3 "$ROOT/tests/integration/test_firstboot_secrets.py"
python3 "$ROOT/tests/integration/test_phase2_payload.py"
echo "Integration tests passed."
