"""Tests for updater signature gate (stable refuses unsigned) and signing round-trip."""
from __future__ import annotations

import json
import os
import subprocess
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


def _openssl_available() -> bool:
    try:
        subprocess.run(["openssl", "version"], capture_output=True, check=True, timeout=5)
        return True
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False


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


def test_signing_round_trip_temp_key():
    """Generate temp RSA key, sign checksums, verify_signature accepts on stable."""
    if not _openssl_available():
        print("SKIP test_signing_round_trip_temp_key (openssl missing)")
        return
    os.environ.pop("ATLAS_ALLOW_UNSIGNED", None)
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        key = td_path / "test.key"
        pub = td_path / "test.pub"  # sign-update-bundle.sh derives KEY.pub from KEY.key
        subprocess.run(
            ["openssl", "genrsa", "-out", str(key), "2048"],
            check=True,
            capture_output=True,
            timeout=30,
        )
        subprocess.run(
            ["openssl", "rsa", "-in", str(key), "-pubout", "-out", str(pub)],
            check=True,
            capture_output=True,
            timeout=30,
        )

        stage = td_path / "stage"
        stage.mkdir()
        payload = stage / "payload" / "srv" / "atlas" / "update-demo"
        payload.mkdir(parents=True)
        (payload / "marker.txt").write_text("signed-v2", encoding="utf-8")
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
        (stage / "RELEASE_NOTES.txt").write_text("signed\n", encoding="utf-8")
        os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
        bundle = td_path / "signed.atlas-update"
        updater.build_update_bundle(stage, bundle)
        os.environ.pop("ATLAS_ALLOW_UNSIGNED", None)

        script = ROOT / "scripts" / "sign-update-bundle.sh"
        proc = subprocess.run(
            ["bash", str(script), str(bundle), "--key", str(key)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 0, proc.stderr + proc.stdout

        keys_dir = td_path / "keys"
        keys_dir.mkdir()
        (keys_dir / "atlas-dev-package.pub").write_bytes(pub.read_bytes())

        with tempfile.TemporaryDirectory() as extract_td:
            root = updater._extract_bundle(bundle, Path(extract_td))
            assert updater.verify_signature(
                root / "update.json",
                allowed_keys_dir=keys_dir,
                channel="stable",
            )

        install = td_path / "root"
        demo = install / "srv" / "atlas" / "update-demo"
        demo.mkdir(parents=True)
        (demo / "marker.txt").write_text("v1", encoding="utf-8")

        real_verify = updater.verify_signature

        def _verify(manifest_path, allowed_keys_dir=None, *, channel=None):
            return real_verify(manifest_path, allowed_keys_dir or keys_dir, channel=channel)

        with patch.object(updater, "verify_signature", side_effect=_verify):
            result = updater.apply_update(
                bundle,
                atlas_data=td_path / "srv-data",
                install_root=install,
                skip_health=True,
            )
        assert result.ok, result.detail
        assert (demo / "marker.txt").read_text() == "signed-v2"


def test_ensure_disk_space_raises_when_short():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td)
        with patch.object(updater, "disk_free_bytes", return_value=1024):
            try:
                updater.ensure_disk_space(path, 10 * 1024 * 1024, label="test")
                assert False, "expected UpdateError"
            except updater.UpdateError as e:
                assert "insufficient disk space" in str(e)
                assert "test" in str(e)


def test_ensure_disk_space_ok_when_enough():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td)
        with patch.object(updater, "disk_free_bytes", return_value=100 * 1024 * 1024):
            updater.ensure_disk_space(path, 10 * 1024 * 1024, label="test")


def test_apply_preflight_disk_space():
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
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (stage / "RELEASE_NOTES.txt").write_text("disk\n", encoding="utf-8")
            bundle = td_path / "b.atlas-update"
            updater.build_update_bundle(stage, bundle)
            with patch.object(updater, "disk_free_bytes", return_value=0):
                result = updater.apply_update(
                    bundle,
                    atlas_data=td_path / "srv-data",
                    install_root=install,
                    skip_health=True,
                )
            assert not result.ok
            assert "disk space" in result.detail.lower()
            assert (demo / "marker.txt").read_text() == "v1"
    finally:
        os.environ.pop("ATLAS_ALLOW_UNSIGNED", None)


if __name__ == "__main__":
    test_dev_unsigned_refused_on_stable_without_env()
    test_dev_unsigned_allowed_with_env()
    test_missing_signature_refused_on_stable()
    test_missing_signature_allowed_with_env()
    test_apply_refuses_unsigned_on_stable()
    test_apply_accepts_unsigned_when_env_set()
    test_channel_allows_unsigned_stable_false()
    test_signing_round_trip_temp_key()
    test_ensure_disk_space_raises_when_short()
    test_ensure_disk_space_ok_when_enough()
    test_apply_preflight_disk_space()
    print("All updater signing gate tests passed!")
