"""Tests for updater signature gate (stable refuses unsigned)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "atlas-updater" / "usr" / "lib" / "atlas"))

import updater  # noqa: E402


def _manifest(staging: Path, **extra) -> Path:
    data = {
        "schema": "atlas.update/v1",
        "from_version": "0.1.0",
        "to_version": "0.1.1",
        "publisher": "atlas-os",
        "digest": "sha256:" + "a" * 64,
        "channel": "stable",
    }
    data.update(extra)
    path = staging / "update.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def test_dev_unsigned_refused_on_stable_without_env():
    os.environ.pop("ATLAS_ALLOW_UNSIGNED", None)
    with tempfile.TemporaryDirectory() as td:
        staging = Path(td)
        manifest = _manifest(staging)
        (staging / "checksums.sha256").write_text("deadbeef  update.json\n", encoding="utf-8")
        (staging / "signature").write_text("DEV-UNSIGNED-PLACEHOLDER\n", encoding="utf-8")
        with patch.object(updater, "get_installed_version", return_value={"version": "0.1.0", "channel": "stable"}):
            assert updater.verify_signature(manifest, channel="stable") is False


def test_dev_unsigned_allowed_with_env():
    os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
    try:
        with tempfile.TemporaryDirectory() as td:
            staging = Path(td)
            manifest = _manifest(staging)
            (staging / "checksums.sha256").write_text("deadbeef  update.json\n", encoding="utf-8")
            (staging / "signature").write_text("DEV-UNSIGNED-PLACEHOLDER\n", encoding="utf-8")
            assert updater.verify_signature(manifest, channel="stable") is True
    finally:
        os.environ.pop("ATLAS_ALLOW_UNSIGNED", None)


def test_missing_signature_refused_on_stable():
    os.environ.pop("ATLAS_ALLOW_UNSIGNED", None)
    with tempfile.TemporaryDirectory() as td:
        staging = Path(td)
        manifest = _manifest(staging)
        (staging / "checksums.sha256").write_text("deadbeef  update.json\n", encoding="utf-8")
        assert updater.verify_signature(manifest, channel="stable") is False


def test_missing_signature_allowed_with_env():
    os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
    try:
        with tempfile.TemporaryDirectory() as td:
            staging = Path(td)
            manifest = _manifest(staging)
            assert updater.verify_signature(manifest, channel="release") is True
    finally:
        os.environ.pop("ATLAS_ALLOW_UNSIGNED", None)


def test_apply_refuses_unsigned_on_stable():
    """End-to-end: apply_update rejects DEV-UNSIGNED when env unset."""
    os.environ.pop("ATLAS_ALLOW_UNSIGNED", None)
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        install = td_path / "root"
        demo = install / "srv" / "atlas" / "update-demo"
        demo.mkdir(parents=True)
        (demo / "marker.txt").write_text("v1", encoding="utf-8")
        stage = td_path / "stage"
        stage.mkdir()
        payload = stage / "payload" / "srv" / "atlas" / "update-demo"
        payload.mkdir(parents=True)
        (payload / "marker.txt").write_text("v2", encoding="utf-8")
        (stage / "update.json").write_text(
            json.dumps(
                {
                    "schema": "atlas.update/v1",
                    "from_version": "0.1.0",
                    "to_version": "0.1.1",
                    "publisher": "atlas-os",
                    "digest": "sha256:" + "0" * 64,
                    "channel": "stable",
                    "reboot_required": False,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (stage / "RELEASE_NOTES.txt").write_text("unsigned test\n", encoding="utf-8")
        # build_update_bundle always writes DEV-UNSIGNED-PLACEHOLDER
        os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
        bundle = td_path / "unsigned.atlas-update"
        updater.build_update_bundle(stage, bundle)
        os.environ.pop("ATLAS_ALLOW_UNSIGNED", None)

        with patch.object(
            updater,
            "get_installed_version",
            return_value={"version": "0.1.0", "channel": "stable"},
        ):
            result = updater.apply_update(
                bundle,
                atlas_data=td_path / "srv-data",
                install_root=install,
                skip_health=True,
            )
        assert not result.ok
        assert "signature" in result.detail.lower()
        assert (demo / "marker.txt").read_text() == "v1"


def test_apply_accepts_unsigned_when_env_set():
    os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
    try:
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            install = td_path / "root"
            demo = install / "srv" / "atlas" / "update-demo"
            demo.mkdir(parents=True)
            (demo / "marker.txt").write_text("v1", encoding="utf-8")
            stage = td_path / "stage"
            stage.mkdir()
            payload = stage / "payload" / "srv" / "atlas" / "update-demo"
            payload.mkdir(parents=True)
            (payload / "marker.txt").write_text("v2-allowed", encoding="utf-8")
            (stage / "update.json").write_text(
                json.dumps(
                    {
                        "schema": "atlas.update/v1",
                        "from_version": "0.1.0",
                        "to_version": "0.1.1",
                        "publisher": "atlas-os",
                        "digest": "sha256:" + "0" * 64,
                        "channel": "stable",
                        "reboot_required": False,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (stage / "RELEASE_NOTES.txt").write_text("allowed\n", encoding="utf-8")
            bundle = td_path / "unsigned.atlas-update"
            updater.build_update_bundle(stage, bundle)
            result = updater.apply_update(
                bundle,
                atlas_data=td_path / "srv-data",
                install_root=install,
                skip_health=True,
            )
            assert result.ok, result.detail
            assert (demo / "marker.txt").read_text() == "v2-allowed"
    finally:
        os.environ.pop("ATLAS_ALLOW_UNSIGNED", None)


def test_channel_allows_unsigned_stable_false():
    os.environ.pop("ATLAS_ALLOW_UNSIGNED", None)
    with patch.object(updater, "get_installed_version", return_value={"channel": "stable"}):
        assert updater._channel_allows_unsigned("stable") is False
        assert updater._channel_allows_unsigned("release") is False


if __name__ == "__main__":
    test_dev_unsigned_refused_on_stable_without_env()
    test_dev_unsigned_allowed_with_env()
    test_missing_signature_refused_on_stable()
    test_missing_signature_allowed_with_env()
    test_apply_refuses_unsigned_on_stable()
    test_apply_accepts_unsigned_when_env_set()
    test_channel_allows_unsigned_stable_false()
    print("All updater signing gate tests passed!")
