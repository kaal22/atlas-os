#!/usr/bin/env python3
"""Unit tests for APT / OS update helpers (no real apt)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "atlas-updater" / "usr" / "lib" / "atlas"))

from os_updater import (  # noqa: E402
    apply_os_updates,
    check_os_updates,
    enable_local_source,
    parse_upgradable_lines,
)


def test_parse_upgradable_atlas_only():
    text = """\
Listing...
atlas-updater/atlas 0.1.1 all [upgradable from: 0.1.0]
libc6/stable 2.36-9 amd64 [upgradable from: 2.36-8]
atlas-command-centre/atlas 0.1.1 all [upgradable from: 0.1.0]
"""
    rows = parse_upgradable_lines(text, atlas_only=True)
    assert [r["name"] for r in rows] == ["atlas-updater", "atlas-command-centre"]
    assert rows[0]["from"] == "0.1.0"
    assert rows[0]["to"] == "0.1.1"
    all_rows = parse_upgradable_lines(text, atlas_only=False)
    assert len(all_rows) == 3


def test_check_and_apply_mocked():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        state = td_path / "os-status.json"
        calls: list[list[str]] = []

        def runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            if cmd[:2] == ["apt-get", "update"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            if cmd[:2] == ["apt", "list"]:
                out = (
                    "Listing...\n"
                    "atlas-updater/atlas 0.1.1 all [upgradable from: 0.1.0]\n"
                )
                return subprocess.CompletedProcess(cmd, 0, stdout=out, stderr="")
            if cmd[0] == "apt-get" and "install" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="Setting up atlas-updater\n", stderr="")
            if cmd[0] == "dpkg-query":
                return subprocess.CompletedProcess(
                    cmd, 0, stdout="atlas-updater\t0.1.0\tinstall ok installed\n", stderr=""
                )
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="unexpected")

        checked = check_os_updates(state_file=state, runner=runner, refresh=True)
        assert checked["ok"]
        assert checked["upgradable"][0]["name"] == "atlas-updater"

        applied = apply_os_updates(state_file=state, runner=runner, atlas_only=True)
        assert applied["ok"]
        assert any(c[0] == "apt-get" and "--only-upgrade" in c for c in calls)

        blocked = apply_os_updates(
            state_file=state,
            runner=runner,
            full_system=True,
            owner_confirmed=False,
        )
        assert not blocked["ok"]
        assert blocked["error"] == "owner_confirmation_required"


def test_enable_local_source_dry():
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "apt-repo"
        (repo / "pool").mkdir(parents=True)
        (repo / "dists").mkdir()
        # Do not write /etc — only render
        body = enable_local_source(repo, write_sources=False)
        assert body["ok"]
        assert "file:" in body["line"]
        assert body["written"] is False


if __name__ == "__main__":
    test_parse_upgradable_atlas_only()
    test_check_and_apply_mocked()
    test_enable_local_source_dry()
    print("OK test_os_updater")
