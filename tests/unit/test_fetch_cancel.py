#!/usr/bin/env python3
"""Tests for cancellable map tile and ZIM downloads."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "atlas-content-manager" / "usr" / "lib" / "atlas"))

from content_manager import (  # noqa: E402
    FetchCancelledError,
    MIN_USABLE_PMTILES_BYTES,
    PackError,
    _download_url_to_file,
    fetch_country_pmtiles,
    read_maps_fetch_progress,
    read_zim_fetch_progress,
    register_fetch_cancel,
    request_cancel_maps_fetch,
    request_cancel_zim_fetch,
    unregister_fetch_cancel,
    write_maps_fetch_progress,
    write_zim_fetch_progress,
)


def test_request_cancel_maps_fetch_not_running():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        result = request_cancel_maps_fetch(root, "uk")
        assert result["ok"] is False
        assert result["error"] == "not_running"


def test_request_cancel_maps_fetch_writes_cancelled_progress():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_maps_fetch_progress(
            root,
            {"country": "uk", "status": "downloading", "done": False, "downloaded": 10, "total": 100},
            "uk",
        )
        event, key = register_fetch_cancel("maps", "uk", partials=[])
        try:
            result = request_cancel_maps_fetch(root, "uk", pack_id="atlas.maps.uk")
        finally:
            unregister_fetch_cancel(key)
        assert result["ok"] is True
        assert result["status"] == "cancelled"
        assert event.is_set()
        prog = read_maps_fetch_progress(root, "uk")
        assert prog["status"] == "cancelled"
        assert prog["done"] is True


def test_request_cancel_zim_fetch_writes_cancelled_progress():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_zim_fetch_progress(
            root,
            {"pack_slug": "wikipedia-en", "status": "downloading", "done": False, "downloaded": 1, "total": 9},
            "wikipedia-en",
        )
        event, key = register_fetch_cancel("zim", "wikipedia-en", partials=[])
        try:
            result = request_cancel_zim_fetch(root, "wikipedia-en", pack_id="atlas.knowledge.wikipedia-en")
        finally:
            unregister_fetch_cancel(key)
        assert result["ok"] is True
        assert event.is_set()
        prog = read_zim_fetch_progress(root, "wikipedia-en")
        assert prog["status"] == "cancelled"
        assert prog["done"] is True


def test_download_url_to_file_honours_cancel_event():
    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / "uk.pmtiles"
        cancel = threading.Event()
        fake = b"x" * (MIN_USABLE_PMTILES_BYTES + 1)
        reads = {"n": 0}

        class _Resp:
            headers = {"Content-Length": str(len(fake))}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, n: int = -1):
                reads["n"] += 1
                if reads["n"] == 1:
                    cancel.set()
                    return fake[:1024]
                return fake[1024:2048] if reads["n"] == 2 else b""

        with mock.patch("content_manager.urllib.request.urlopen", return_value=_Resp()):
            try:
                _download_url_to_file("https://example.test/uk.pmtiles", dest, cancel_event=cancel)
                raise AssertionError("expected FetchCancelledError")
            except FetchCancelledError:
                pass
        assert not dest.exists()
        assert not dest.with_suffix(dest.suffix + ".partial").exists()


def test_fetch_country_pmtiles_cancel_during_extract():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        dest = td_path / "maps" / "nl"
        atlas = td_path / "atlas"
        cli = td_path / "pmtiles"
        cli.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
        cli.chmod(0o755)

        def _slow_popen(cmd, **kwargs):
            import io

            partial = Path(cmd[3])
            proc = mock.Mock()
            proc.poll = mock.Mock(side_effect=[None, None, None])
            proc.returncode = -9
            proc.stdout = None
            proc.stderr = io.StringIO("")
            proc.kill = mock.Mock(side_effect=lambda: partial.write_bytes(b"partial"))
            proc.wait = mock.Mock(return_value=0)
            return proc

        with mock.patch("content_manager.ensure_pmtiles_cli", return_value=cli), mock.patch(
            "content_manager.resolve_protomaps_planet_url",
            return_value="https://build.protomaps.com/20260721.pmtiles",
        ), mock.patch("content_manager.subprocess.Popen", side_effect=_slow_popen), mock.patch(
            "content_manager.time.sleep",
            side_effect=lambda _s: request_cancel_maps_fetch(atlas, "nl"),
        ):
            try:
                fetch_country_pmtiles(
                    dest,
                    country="nl",
                    bbox=[3.3, 50.7, 7.3, 53.6],
                    maxzoom=8,
                    atlas_root=atlas,
                    size_hint_bytes=80_000_000,
                )
                raise AssertionError("expected FetchCancelledError")
            except FetchCancelledError:
                pass
        prog = read_maps_fetch_progress(atlas, "nl")
        assert prog["status"] == "cancelled"
        assert prog["done"] is True


if __name__ == "__main__":
    test_request_cancel_maps_fetch_not_running()
    test_request_cancel_maps_fetch_writes_cancelled_progress()
    test_request_cancel_zim_fetch_writes_cancelled_progress()
    test_download_url_to_file_honours_cancel_event()
    test_fetch_country_pmtiles_cancel_during_extract()
    print("OK test_fetch_cancel")
