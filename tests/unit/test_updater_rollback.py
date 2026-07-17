#!/usr/bin/env python3
"""Unit tests for atlas updater rollback."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "atlas-updater" / "usr" / "lib" / "atlas"))

from updater import (  # noqa: E402
    apply_update,
    build_update_bundle,
)


def _make_bundle(stage: Path, out: Path, *, force_fail: bool = False, content: str = "v2") -> Path:
    # Paths under srv/atlas — writable by Command Centre (ProtectSystem=strict)
    payload = stage / "payload" / "srv" / "atlas" / "update-demo"
    payload.mkdir(parents=True)
    (payload / "marker.txt").write_text(content, encoding="utf-8")
    if force_fail:
        (stage / "payload" / ".force-health-fail").write_text("1", encoding="utf-8")
    manifest = {
        "schema": "atlas.update/v1",
        "from_version": "0.1.0",
        "to_version": "0.1.1-broken" if force_fail else "0.1.1",
        "publisher": "atlas-os",
        "digest": "sha256:" + "0" * 64,
        "reboot_required": False,
        "health_urls": ["http://127.0.0.1:9/never"],
        "force_health_fail": force_fail,
    }
    (stage / "update.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (stage / "RELEASE_NOTES.txt").write_text("Test update\n", encoding="utf-8")
    os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
    build_update_bundle(stage, out)
    return out


def test_good_apply():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        install = td_path / "root"
        demo = install / "srv" / "atlas" / "update-demo"
        demo.mkdir(parents=True)
        (demo / "marker.txt").write_text("v1", encoding="utf-8")
        atlas_data = td_path / "srv-data"
        stage = td_path / "stage"
        stage.mkdir()
        bundle = _make_bundle(stage, td_path / "good.atlas-update", content="v2-good")
        result = apply_update(
            bundle,
            atlas_data=atlas_data,
            install_root=install,
            skip_health=True,
        )
        assert result.ok, result.detail
        assert (demo / "marker.txt").read_text() == "v2-good"


def test_broken_apply_rolls_back():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        install = td_path / "root"
        demo = install / "srv" / "atlas" / "update-demo"
        demo.mkdir(parents=True)
        (demo / "marker.txt").write_text("v1-safe", encoding="utf-8")
        atlas_data = td_path / "srv-data"
        stage = td_path / "stage"
        stage.mkdir()
        bundle = _make_bundle(stage, td_path / "bad.atlas-update", force_fail=True, content="v2-bad")
        result = apply_update(
            bundle,
            atlas_data=atlas_data,
            install_root=install,
            skip_health=False,
        )
        assert not result.ok
        assert result.rolled_back
        assert (demo / "marker.txt").read_text() == "v1-safe"
        logs = list((atlas_data / "logs").glob("update-*.json"))
        assert logs, "expected diagnostics log"


if __name__ == "__main__":
    test_good_apply()
    test_broken_apply_rolls_back()
    print("OK test_updater_rollback")
