#!/usr/bin/env python3
"""System daemon capability token expiry + allowlist."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "atlas-system-daemon" / "usr" / "lib" / "atlas"))

_tmpdir = tempfile.mkdtemp(prefix="atlas-daemon-test-")
os.environ["ATLAS_AUDIT_LOG"] = str(Path(_tmpdir) / "audit.jsonl")
os.environ["ATLAS_NETWORK_MODE_FILE"] = str(Path(_tmpdir) / "network-mode")

import system_daemon as sd  # noqa: E402

sd.AUDIT_LOG = Path(os.environ["ATLAS_AUDIT_LOG"])
sd.NETWORK_MODE_PATH = Path(os.environ["ATLAS_NETWORK_MODE_FILE"])


def test_unknown_method_rejected():
    resp = sd.handle({"method": "evil.root", "token": "cap:*:abc"})
    assert resp["ok"] is False
    assert resp["error"] == "unknown_method"


def test_bad_token_rejected():
    resp = sd.handle({"method": "system.health.read", "token": "nope"})
    assert resp["ok"] is False
    assert resp["error"] == "unauthorized"


def test_expired_token_rejected():
    expired = f"cap:system.health.read:nonce:{int(time.time()) - 10}"
    assert sd.verify_token(expired, "system.health.read") is False
    resp = sd.handle({"method": "system.health.read", "token": expired})
    assert resp["ok"] is False


def test_valid_token_with_exp_accepted():
    tok = f"cap:system.health.read:nonce:{int(time.time()) + 60}"
    assert sd.verify_token(tok, "system.health.read") is True
    resp = sd.handle({"method": "system.health.read", "token": tok})
    assert resp["ok"] is True


def test_network_mode_private_dry_run():
    tok = f"cap:network.mode.apply:nonce:{int(time.time()) + 60}"
    resp = sd.handle({
        "method": "network.mode.apply",
        "token": tok,
        "params": {"mode": "private_device", "dry_run": True},
    })
    assert resp["ok"] is True
    assert resp.get("dry_run") is True
    assert any("deny incoming" in c for c in resp.get("commands", []))
    # intent persisted for private_device
    assert sd.NETWORK_MODE_PATH.exists()
    assert sd.NETWORK_MODE_PATH.read_text().strip() == "private_device"


def test_non_private_requires_owner():
    tok = f"cap:network.mode.apply:nonce:{int(time.time()) + 60}"
    resp = sd.handle({
        "method": "network.mode.apply",
        "token": tok,
        "params": {"mode": "trusted_lan", "role": "user"},
    })
    assert resp["ok"] is False
    assert resp.get("error") == "owner_confirmation_required"


def test_audit_written():
    tok = f"cap:system.health.read:nonce:{int(time.time()) + 60}"
    sd.handle({"method": "system.health.read", "token": tok})
    lines = sd.AUDIT_LOG.read_text(encoding="utf-8").strip().splitlines()
    assert lines
    last = json.loads(lines[-1])
    assert last.get("source") == "system_daemon"


if __name__ == "__main__":
    test_unknown_method_rejected()
    test_bad_token_rejected()
    test_expired_token_rejected()
    test_valid_token_with_exp_accepted()
    test_network_mode_private_dry_run()
    test_non_private_requires_owner()
    test_audit_written()
    print("OK test_daemon_tokens")
