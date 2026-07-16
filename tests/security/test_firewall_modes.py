#!/usr/bin/env python3
"""Firewall / network mode matrix aligned with network_modes.py (product §23)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "atlas-system-daemon" / "usr" / "lib" / "atlas"))

from network_modes import apply_mode  # noqa: E402

MODES = {
    "private_device": {
        "bind": "127.0.0.1",
        "lan_access": False,
        "hotspot": False,
        "ssh": False,
    },
    "trusted_lan": {
        "bind": "lan",
        "lan_access": True,
        "hotspot": False,
        "ssh": False,
        "requires_auth": True,
    },
    "private_hotspot": {
        "bind": "hotspot",
        "lan_access": False,
        "hotspot": True,
        "ssh": False,
        "requires_auth": True,
    },
    "offline_isolation": {
        "bind": "127.0.0.1",
        "lan_access": False,
        "hotspot": False,
        "ssh": False,
        "egress": False,
    },
}


def default_mode() -> str:
    return "private_device"


def allows_unauthenticated_lan(mode: str) -> bool:
    cfg = MODES[mode]
    if not cfg.get("lan_access"):
        return False
    return not cfg.get("requires_auth", True)


def test_default_is_private():
    assert default_mode() == "private_device"
    assert allows_unauthenticated_lan("private_device") is False


def test_trusted_lan_still_requires_auth():
    assert allows_unauthenticated_lan("trusted_lan") is False


def test_isolation_no_egress():
    assert MODES["offline_isolation"].get("egress") is False


def test_private_device_commands():
    cmds = apply_mode("private_device", dry_run=True)
    assert any("default deny incoming" in c for c in cmds)
    assert any("allow in on lo" in c for c in cmds)
    # Must not open LAN to 8787
    assert not any("port 8787" in c for c in cmds)
    assert any("--force enable" in c for c in cmds)


def test_trusted_lan_opens_8787_but_private_does_not():
    private = apply_mode("private_device", dry_run=True)
    trusted = apply_mode("trusted_lan", dry_run=True)
    assert not any("port 8787" in c for c in private)
    assert any("port 8787" in c for c in trusted)


def test_offline_isolation_denies_egress():
    cmds = apply_mode("offline_isolation", dry_run=True)
    assert any("default deny outgoing" in c for c in cmds)


if __name__ == "__main__":
    test_default_is_private()
    test_trusted_lan_still_requires_auth()
    test_isolation_no_egress()
    test_private_device_commands()
    test_trusted_lan_opens_8787_but_private_does_not()
    test_offline_isolation_denies_egress()
    print("OK test_firewall_modes")
