#!/usr/bin/env python3
"""Firewall / network mode matrix (product §23)."""

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


if __name__ == "__main__":
    test_default_is_private()
    test_trusted_lan_still_requires_auth()
    test_isolation_no_egress()
    print("OK test_firewall_modes")
