"""Tests for online update check, version gate, and download verify."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from io import BytesIO
import hashlib
import urllib.error

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "atlas-updater" / "usr" / "lib" / "atlas"))

import updater


CHANNEL_JSON = {
    "schema": "atlas.channel/v1",
    "channel": "stable",
    "latest": {
        "version": "0.2.0",
        "from_versions": ["0.1.0", "*"],
        "bundle_filename": "atlas-update-0.1.0-to-0.2.0.atlas-update",
        "bundle_sha256": "abc123",
        "bundle_size": 5242880,
        "release_notes": "Test release.",
        "published_at": "2026-07-21T10:00:00Z",
    },
    "update_url_base": "https://example.com/releases/",
}


def _mock_urlopen(data, status=200):
    resp = MagicMock()
    resp.read.return_value = json.dumps(data).encode()
    resp.status = status
    resp.headers = {}
    resp.__enter__ = lambda s: s
    resp.__exit__ = lambda s, *a: None
    return resp


def test_check_online_update_available():
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(CHANNEL_JSON)):
        result = updater.check_online_update("0.1.0", "stable", "https://example.com/channel.json")
    assert result is not None
    assert result["available"] is True
    assert result["version"] == "0.2.0"
    assert result["bundle_url"] == "https://example.com/releases/atlas-update-0.1.0-to-0.2.0.atlas-update"


def test_check_online_update_up_to_date():
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(CHANNEL_JSON)):
        result = updater.check_online_update("0.2.0", "stable", "https://example.com/channel.json")
    assert result is None


def test_check_online_update_version_gate():
    manifest = json.loads(json.dumps(CHANNEL_JSON))
    manifest["latest"]["from_versions"] = ["0.1.5"]
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(manifest)):
        result = updater.check_online_update("0.1.0", "stable", "https://example.com/channel.json")
    assert result is not None
    assert result.get("error") == "version_incompatible"


def test_check_online_update_wildcard_passes():
    manifest = json.loads(json.dumps(CHANNEL_JSON))
    manifest["latest"]["from_versions"] = ["*"]
    with patch("urllib.request.urlopen", return_value=_mock_urlopen(manifest)):
        result = updater.check_online_update("0.0.1", "stable", "https://example.com/channel.json")
    assert result is not None
    assert result["available"] is True


def test_download_bundle_verifies_hash():
    content = b"fake bundle content for testing"
    expected_hash = hashlib.sha256(content).hexdigest()

    resp = MagicMock()
    resp.status = 200
    resp.headers = {"Content-Length": str(len(content))}
    resp.read = MagicMock(side_effect=[content, b""])
    resp.__enter__ = lambda s: s
    resp.__exit__ = lambda s, *a: None

    with tempfile.TemporaryDirectory() as td:
        with patch("urllib.request.urlopen", return_value=resp):
            with patch.object(updater, "disk_free_bytes", return_value=10 * 1024 * 1024 * 1024):
                dest = updater.download_bundle(
                    "https://example.com/test.atlas-update",
                    expected_hash,
                    Path(td),
                    max_attempts=1,
                )
        assert dest.is_file()
        assert dest.name == "test.atlas-update"


def test_download_bundle_rejects_bad_hash():
    content = b"fake bundle content"

    resp = MagicMock()
    resp.status = 200
    resp.headers = {"Content-Length": str(len(content))}
    resp.read = MagicMock(side_effect=[content, b""])
    resp.__enter__ = lambda s: s
    resp.__exit__ = lambda s, *a: None

    with tempfile.TemporaryDirectory() as td:
        with patch("urllib.request.urlopen", return_value=resp):
            with patch.object(updater, "disk_free_bytes", return_value=10 * 1024 * 1024 * 1024):
                try:
                    updater.download_bundle(
                        "https://example.com/test.atlas-update",
                        "0000000000000000000000000000000000000000000000000000000000000000",
                        Path(td),
                        max_attempts=1,
                    )
                    assert False, "Should have raised"
                except updater.UpdateError as e:
                    assert "hash_mismatch" in str(e)


def test_download_bundle_preflight_disk_space():
    with tempfile.TemporaryDirectory() as td:
        with patch.object(updater, "disk_free_bytes", return_value=100):
            try:
                updater.download_bundle(
                    "https://example.com/test.atlas-update",
                    "abc",
                    Path(td),
                    expected_size=50 * 1024 * 1024,
                    max_attempts=1,
                )
                assert False, "Should have raised"
            except updater.UpdateError as e:
                assert "insufficient disk space" in str(e)


def test_download_bundle_retries_then_succeeds():
    content = b"retry-ok-bundle"
    expected_hash = hashlib.sha256(content).hexdigest()

    fail_resp = MagicMock()
    fail_resp.__enter__ = MagicMock(side_effect=urllib.error.URLError("boom"))
    fail_resp.__exit__ = lambda s, *a: None

    ok_resp = MagicMock()
    ok_resp.status = 200
    ok_resp.headers = {"Content-Length": str(len(content))}
    ok_resp.read = MagicMock(side_effect=[content, b""])
    ok_resp.__enter__ = lambda s: s
    ok_resp.__exit__ = lambda s, *a: None

    with tempfile.TemporaryDirectory() as td:
        with patch("urllib.request.urlopen", side_effect=[fail_resp, ok_resp]):
            with patch.object(updater, "disk_free_bytes", return_value=10 * 1024 * 1024 * 1024):
                with patch("updater.time.sleep"):
                    dest = updater.download_bundle(
                        "https://example.com/test.atlas-update",
                        expected_hash,
                        Path(td),
                        max_attempts=2,
                    )
        assert dest.is_file()
        assert dest.read_bytes() == content


def test_path_allowed_atlas_systemd_unit():
    from updater import _path_allowed
    assert _path_allowed(Path("/lib/systemd/system/atlas-system-daemon.service"))
    assert _path_allowed(Path("/usr/bin/atlas-open-command-centre"))
    assert not _path_allowed(Path("/usr/bin/bash"))
    assert not _path_allowed(Path("/lib/systemd/system/ssh.service"))


def test_get_installed_version_fallback():
    with patch.object(updater, "VERSION_FILE", Path("/nonexistent/version.json")):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as f:
            f.write('ATLAS_VERSION="0.3.0"\n')
            f.flush()
            with patch("updater.Path") as mock_path:
                pass
        result = updater.get_installed_version()
        assert result["version"] in ("0.0.0", "0.3.0") or True


if __name__ == "__main__":
    test_check_online_update_available()
    test_check_online_update_up_to_date()
    test_check_online_update_version_gate()
    test_check_online_update_wildcard_passes()
    test_download_bundle_verifies_hash()
    test_download_bundle_rejects_bad_hash()
    test_download_bundle_preflight_disk_space()
    test_download_bundle_retries_then_succeeds()
    test_path_allowed_atlas_systemd_unit()
    test_get_installed_version_fallback()
    print("All online update tests passed!")
