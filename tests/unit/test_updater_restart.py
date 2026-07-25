#!/usr/bin/env python3
"""Unit tests for post-apply restart_services / reboot_required."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "atlas-updater" / "usr" / "lib" / "atlas"))

from updater import (  # noqa: E402
    apply_update,
    build_update_bundle,
    restart_whitelisted_services,
)


def _make_bundle(
    stage: Path,
    out: Path,
    *,
    content: str = "v2",
    reboot_required: bool = False,
    restart_services: list[str] | None = None,
) -> Path:
    payload = stage / "payload" / "srv" / "atlas" / "update-demo"
    payload.mkdir(parents=True)
    (payload / "marker.txt").write_text(content, encoding="utf-8")
    manifest: dict[str, Any] = {
        "schema": "atlas.update/v1",
        "from_version": "0.1.0",
        "to_version": "0.1.2",
        "publisher": "atlas-os",
        "digest": "sha256:" + "0" * 64,
        "reboot_required": reboot_required,
        "health_urls": ["http://127.0.0.1:9/never"],
    }
    if restart_services is not None:
        manifest["restart_services"] = restart_services
    (stage / "update.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (stage / "RELEASE_NOTES.txt").write_text("Restart test\n", encoding="utf-8")
    os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
    build_update_bundle(stage, out)
    return out


def test_restart_whitelist_rejects_arbitrary():
    calls: list[list[str]] = []

    def runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    restarted, errors = restart_whitelisted_services(
        ["atlas-command-centre", "evil.service", "bash -c reboot", "../../etc"],
        runner=runner,
    )
    assert restarted == ["atlas-command-centre"]
    assert any(e["service"] == "evil.service" for e in errors)
    assert any("bash" in e["service"] for e in errors)
    assert calls == [["systemctl", "try-restart", "atlas-command-centre.service"]]


def test_apply_restarts_and_flags_reboot():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        install = td_path / "root"
        demo = install / "srv" / "atlas" / "update-demo"
        demo.mkdir(parents=True)
        (demo / "marker.txt").write_text("v1", encoding="utf-8")
        atlas_data = td_path / "srv-data"
        stage = td_path / "stage"
        stage.mkdir()
        bundle = _make_bundle(
            stage,
            td_path / "restart.atlas-update",
            reboot_required=True,
            restart_services=[
                "atlas-command-centre",
                "atlas-system-daemon",
                "not-allowed.service",
            ],
        )
        calls: list[list[str]] = []

        def runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

        result = apply_update(
            bundle,
            atlas_data=atlas_data,
            install_root=install,
            skip_health=True,
            systemctl_runner=runner,
        )
        assert result.ok, result.detail
        assert result.reboot_required is True
        assert "reboot recommended" in (result.detail or "")
        assert result.restarted_services == ["atlas-command-centre", "atlas-system-daemon"]
        assert result.restart_errors and any(
            e.get("service") == "not-allowed.service" for e in result.restart_errors
        )
        assert [c[2] for c in calls] == [
            "atlas-command-centre.service",
            "atlas-system-daemon.service",
        ]
        body = result.to_dict()
        assert body["reboot_required"] is True
        assert body["restarted_services"] == ["atlas-command-centre", "atlas-system-daemon"]


def test_skip_restart():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        install = td_path / "root"
        demo = install / "srv" / "atlas" / "update-demo"
        demo.mkdir(parents=True)
        (demo / "marker.txt").write_text("v1", encoding="utf-8")
        atlas_data = td_path / "srv-data"
        stage = td_path / "stage"
        stage.mkdir()
        bundle = _make_bundle(
            stage,
            td_path / "norestart.atlas-update",
            restart_services=["atlas-command-centre"],
        )
        calls: list[list[str]] = []

        def runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        result = apply_update(
            bundle,
            atlas_data=atlas_data,
            install_root=install,
            skip_health=True,
            skip_restart=True,
            systemctl_runner=runner,
        )
        assert result.ok
        assert not calls
        assert result.restarted_services is None


if __name__ == "__main__":
    test_restart_whitelist_rejects_arbitrary()
    test_apply_restarts_and_flags_reboot()
    test_skip_restart()
    print("OK test_updater_restart")
