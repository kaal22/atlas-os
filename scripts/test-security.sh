#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "== Atlas security tests =="
python3 "$ROOT/tests/security/test_no_docker_sock_in_ui.py"
python3 "$ROOT/tests/security/test_capability_escalation.py"
python3 "$ROOT/tests/security/test_firewall_modes.py"
python3 "$ROOT/tests/security/test_auth_sessions.py"
python3 "$ROOT/tests/security/test_cc_no_privileged_subprocess.py"
python3 "$ROOT/tests/security/test_daemon_tokens.py"
echo "Security tests passed."
