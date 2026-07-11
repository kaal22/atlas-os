#!/usr/bin/env python3
"""Capability escalation must fail closed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))
from test_policy_levels import can_auto_run, is_prohibited  # noqa: E402


def test_child_cannot_gain_shell():
    assert is_prohibited("host.root_shell")
    assert can_auto_run(4, "host.root_shell") is False


def test_level4_never_auto():
    assert can_auto_run(4, "backup.restore") is False


if __name__ == "__main__":
    test_child_cannot_gain_shell()
    test_level4_never_auto()
    print("OK test_capability_escalation")
