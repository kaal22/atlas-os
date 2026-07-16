#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "== Atlas unit tests =="
"$ROOT/scripts/validate-catalog.sh" "$ROOT/release/sources.catalog.yaml"
python3 "$ROOT/tests/unit/test_policy_levels.py"
python3 "$ROOT/tests/unit/test_pack_manifest.py"
python3 "$ROOT/tests/unit/test_task_fsm.py"
python3 "$ROOT/tests/unit/test_hardware_recommend.py"
python3 "$ROOT/tests/unit/test_gpu_detect.py"
python3 "$ROOT/tests/unit/test_agent_ollama_loop.py"
python3 "$ROOT/tests/unit/test_model_catalog.py"
echo "All unit tests passed."
