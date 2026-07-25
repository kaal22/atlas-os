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
    assert any("--force reset" in c for c in cmds)


def test_apply_mode_surfaces_ufw_stderr(monkeypatch=None):
    """Live apply must include ufw stderr, not only CalledProcessError exit code."""
    import network_modes as nm

    class FakeProc:
        def __init__(self, returncode=1, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    calls = {"n": 0}

    def fake_run(cmd, **kwargs):
        calls["n"] += 1
        # First call is `ufw status` from apply_mode
        if len(cmd) >= 2 and cmd[1] == "status":
            return FakeProc(0, stdout="Status: inactive\n")
        return FakeProc(1, stderr="ERROR: problem running ufw-init\n")

    orig_run = nm.subprocess.run
    orig_bin = nm.ufw_binary
    nm.ufw_binary = lambda: "/usr/sbin/ufw"  # type: ignore[assignment]
    nm.subprocess.run = fake_run  # type: ignore[assignment]
    try:
        try:
            apply_mode("private_device", dry_run=False)
            raise AssertionError("expected UfwApplyError")
        except nm.UfwApplyError as e:
            assert e.reason == "inactive"
            msg = str(e)
            assert "inactive" in msg.lower()
            assert "problem running ufw-init" in (e.detail or msg)
    finally:
        nm.subprocess.run = orig_run  # type: ignore[assignment]
        nm.ufw_binary = orig_bin  # type: ignore[assignment]


def test_apply_mode_missing_ufw():
    import network_modes as nm

    orig_bin = nm.ufw_binary
    nm.ufw_binary = lambda: None  # type: ignore[assignment]
    try:
        try:
            apply_mode("private_device", dry_run=False)
            raise AssertionError("expected UfwApplyError")
        except nm.UfwApplyError as e:
            assert e.reason == "missing"
            assert "ufw not installed" in str(e)
            warn = nm.soft_fail_warning("private_device", e)
            assert "mode saved" in warn
            assert "firewall not applied" in warn
    finally:
        nm.ufw_binary = orig_bin  # type: ignore[assignment]


def test_soft_fail_warning_inactive():
    import network_modes as nm

    err = nm.UfwApplyError("boom", reason="inactive", detail="reset failed")
    warn = nm.soft_fail_warning("private_device", err)
    assert warn.startswith("ufw inactive — mode saved")
    assert "private_device" in warn


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
    test_apply_mode_surfaces_ufw_stderr()
    test_apply_mode_missing_ufw()
    test_soft_fail_warning_inactive()
    test_trusted_lan_opens_8787_but_private_does_not()
    test_offline_isolation_denies_egress()
    print("OK test_firewall_modes")
