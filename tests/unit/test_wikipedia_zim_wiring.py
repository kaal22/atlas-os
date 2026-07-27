#!/usr/bin/env python3
"""Wikipedia ZIM fetch helpers + knowledge pack ingest for agents."""
from __future__ import annotations

import json
import os
import struct
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "atlas-content-manager" / "usr" / "lib" / "atlas"))
sys.path.insert(0, str(ROOT / "packages" / "atlas-knowledge" / "usr" / "lib" / "atlas"))

os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
os.environ["ATLAS_KNOWLEDGE_KEYWORD_ONLY"] = "1"
os.environ["ATLAS_ZIM_SKIP_FETCH"] = "1"  # default: no network in unit tests

from content_manager import (  # noqa: E402
    PackError,
    build_pack,
    fetch_zim_for_manifest,
    install_pack,
    register_zim_with_kiwix,
    should_auto_fetch_zim,
    verify_zim_file,
    write_zim_fetch_progress,
    read_zim_fetch_progress,
    zim_file_complete,
)
from knowledge_service import KnowledgeService  # noqa: E402


def _minimal_zim_bytes(n: int = 64, entry_count: int = 3) -> bytes:
    buf = bytearray(max(n, 32))
    buf[0:4] = b"ZIM\x04"
    struct.pack_into("<I", buf, 24, entry_count)
    return bytes(buf)


def _stage_wiki_pack(stage: Path, mount_target: str, *, with_zim_fetch: bool = True) -> Path:
    payload = stage / "payload" / "articles"
    payload.mkdir(parents=True)
    (payload / "Democracy.md").write_text(
        "# Democracy\n\nDemocracy is rule by the people through elections.\n",
        encoding="utf-8",
    )
    (stage / "licences").mkdir()
    (stage / "licences" / "CC-BY-SA.txt").write_text("CC-BY-SA", encoding="utf-8")
    meta: dict = {"language": "eng", "kind": "wikipedia"}
    if with_zim_fetch:
        meta["zim_fetch"] = {
            "enabled": True,
            "default_url": "https://example.test/wiki.zim",
            "filename": "test.zim",
            "size_hint_bytes": 1000,
        }
    manifest = {
        "schema": "atlas.pack/v1",
        "id": "atlas.knowledge.wikipedia-en.test",
        "version": "1.0.0",
        "type": "atlas.content.knowledge",
        "name": "Test Wikipedia",
        "description": "Unit test",
        "size_bytes": 4096,
        "minimum_os_version": "0.1.0",
        "architectures": ["all"],
        "mount_target": mount_target,
        "licences": ["CC-BY-SA-4.0"],
        "sources": [],
        "dependencies": [],
        "conflicts": [],
        "post_install_workflow": "knowledge.index",
        "meta": meta,
        "digest": "sha256:" + "0" * 64,
    }
    (stage / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    out = stage.parent / "wiki-test.atlas-pack"
    digest = build_pack(stage, out)
    manifest["digest"] = digest
    (stage / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    build_pack(stage, out)
    return out


def test_knowledge_pack_searchable_by_users():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        atlas = td_path / "srv"
        stage = td_path / "stage"
        stage.mkdir()
        target = str(atlas / "knowledge" / "packs" / "wikipedia-en")
        pack = _stage_wiki_pack(stage, target)
        result = install_pack(pack, atlas, fetch_tiles=False)
        assert result["ok"]
        ks = KnowledgeService(atlas / "knowledge", keyword_only=True)
        hits = ks.search("alice", "Democracy elections")
        assert hits, "pack docs ingested as system must be visible to users"
        assert any(h.get("trust") == "pack" for h in hits)
        assert ks.library("bob"), "shared pack corpus appears in library"


def test_should_auto_fetch_zim_respects_skip():
    manifest = {
        "type": "atlas.content.knowledge",
        "id": "atlas.knowledge.wikipedia-en",
        "meta": {"zim_fetch": {"enabled": True, "default_url": "https://example.test/x.zim"}},
    }
    with tempfile.TemporaryDirectory() as td:
        target = Path(td)
        os.environ["ATLAS_ZIM_SKIP_FETCH"] = "1"
        assert should_auto_fetch_zim(manifest, target) is False
        os.environ.pop("ATLAS_ZIM_SKIP_FETCH", None)
        assert should_auto_fetch_zim(manifest, target) is True
        (target / "already.zim").write_bytes(_minimal_zim_bytes(64))
        assert should_auto_fetch_zim(manifest, target) is False


def test_download_resumes_with_http_range():
    """Transient disconnect keeps .partial and resumes via Range."""
    from content_manager import _download_url_to_file

    with tempfile.TemporaryDirectory() as td:
        dest = Path(td) / "big.zim"
        payload = _minimal_zim_bytes(256, entry_count=2) + (b"X" * 256)
        total = len(payload)
        calls = {"n": 0}
        statuses: list[dict] = []

        class _Resp:
            def __init__(self, status, headers, body):
                self.status = status
                self.headers = headers
                self._body = body
                self._off = 0

            def read(self, n=-1):
                if self._off >= len(self._body):
                    return b""
                if n is None or n < 0:
                    chunk = self._body[self._off :]
                    self._off = len(self._body)
                    return chunk
                chunk = self._body[self._off : self._off + n]
                self._off += len(chunk)
                return chunk

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_urlopen(req, timeout=None):
            calls["n"] += 1
            range_h = req.headers.get("Range") or req.get_header("Range") or ""
            if calls["n"] == 1:
                # First attempt: send half then pretend hang/close (short body).
                half = payload[: total // 2]

                class _Boom(_Resp):
                    def read(self, n=-1):
                        if self._off >= len(self._body):
                            raise TimeoutError("simulated drop")
                        return super().read(n)

                return _Boom(200, {"Content-Length": str(total)}, half)
            # Resume
            range_h = ""
            if hasattr(req, "header_items"):
                for k, v in req.header_items():
                    if str(k).lower() == "range":
                        range_h = v
                        break
            if not range_h:
                range_h = getattr(req, "headers", {}).get("Range") or ""
            assert str(range_h).startswith("bytes="), f"expected Range resume, got {range_h!r} headers={getattr(req,'headers',None)}"
            start = int(str(range_h).split("=", 1)[1].split("-", 1)[0])
            body = payload[start:]
            return _Resp(
                206,
                {
                    "Content-Length": str(len(body)),
                    "Content-Range": f"bytes {start}-{total - 1}/{total}",
                },
                body,
            )

        with mock.patch("content_manager.urllib.request.urlopen", side_effect=fake_urlopen), mock.patch(
            "content_manager.ZIM_DOWNLOAD_RETRY_BASE_SEC", 0.01
        ), mock.patch("content_manager.ZIM_DOWNLOAD_RETRY_MAX_SEC", 0.01):
            got, expected = _download_url_to_file(
                "https://example.test/big.zim",
                dest,
                resume=True,
                max_attempts=4,
                status_cb=lambda d: statuses.append(dict(d)),
            )
        assert dest.is_file()
        assert dest.read_bytes() == payload
        assert got == total and expected == total
        assert any(s.get("status") in {"retrying", "resuming"} for s in statuses)


def test_zim_fetch_progress_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        atlas = Path(td)
        write_zim_fetch_progress(
            atlas,
            {"pack_slug": "wikipedia-en", "status": "downloading", "downloaded": 10, "total": 100, "done": False},
            "wikipedia-en",
        )
        st = read_zim_fetch_progress(atlas, "wikipedia-en")
        assert st["status"] == "downloading"
        assert st["downloaded"] == 10


def test_fetch_zim_registers_kiwix(monkeypatch=None):
    with tempfile.TemporaryDirectory() as td:
        atlas = Path(td) / "srv"
        target = atlas / "knowledge" / "packs" / "wikipedia-en"
        target.mkdir(parents=True)
        manifest = {
            "id": "atlas.knowledge.wikipedia-en",
            "name": "Wikipedia EN",
            "description": "test",
            "type": "atlas.content.knowledge",
            "meta": {
                "language": "eng",
                "zim_fetch": {
                    "enabled": True,
                    "default_url": "https://example.test/wiki.zim",
                    "filename": "wiki.zim",
                    "size_hint_bytes": 64,
                },
            },
        }

        def fake_download(url, dest, progress_cb=None, cancel_event=None, **_kwargs):
            dest.parent.mkdir(parents=True, exist_ok=True)
            data = _minimal_zim_bytes(64)
            dest.write_bytes(data)
            if progress_cb:
                progress_cb(len(data), len(data))
            return len(data), len(data)

        with mock.patch("content_manager._http_head_ok", return_value=True), mock.patch(
            "content_manager._download_url_to_file", side_effect=fake_download
        ), mock.patch(
            "content_manager.maybe_extract_zim_html_for_rag",
            return_value={"ok": True, "extracted": 0},
        ), mock.patch(
            "content_manager._workflow_knowledge_index",
            return_value=None,
        ), mock.patch(
            "content_manager._restart_kiwix_serve",
            return_value=None,
        ):
            info = fetch_zim_for_manifest(manifest, target, atlas)
        assert info["ok"]
        assert (target / "wiki.zim").is_file()
        assert (atlas / "kiwix" / "wiki.zim").is_file()
        assert (atlas / "kiwix" / "library.xml").is_file()
        st = read_zim_fetch_progress(atlas, "wikipedia-en")
        assert st["status"] == "ready" and st["done"] is True


def test_incomplete_zim_rejected_and_not_registered():
    with tempfile.TemporaryDirectory() as td:
        atlas = Path(td) / "srv"
        zim = Path(td) / "wikipedia_en_all_mini.zim"
        # Truncated: valid magic but far below 12G catalogue hint.
        zim.write_bytes(_minimal_zim_bytes(4096, entry_count=1000))
        ok, reason = zim_file_complete(zim, size_hint_bytes=12_000_000_000)
        assert ok is False
        assert "incomplete" in reason
        try:
            verify_zim_file(zim, size_hint_bytes=12_000_000_000)
            assert False, "expected PackError"
        except PackError as e:
            assert "incomplete" in str(e)
        try:
            register_zim_with_kiwix(zim, atlas, size_hint_bytes=12_000_000_000)
            assert False, "truncated ZIM must not register"
        except PackError:
            pass
        assert not (atlas / "kiwix" / zim.name).is_file()

        ok2, reason2 = zim_file_complete(zim, expected_bytes=12_000_000_000)
        assert ok2 is False and "incomplete_download" in reason2


def test_should_auto_fetch_when_only_truncated_zim_present():
    with tempfile.TemporaryDirectory() as td:
        target = Path(td)
        zim = target / "wikipedia_en_all_mini.zim"
        zim.write_bytes(_minimal_zim_bytes(4096, entry_count=1))
        os.environ.pop("ATLAS_ZIM_SKIP_FETCH", None)
        manifest = {
            "type": "atlas.content.knowledge",
            "id": "atlas.knowledge.wikipedia-en-mini",
            "meta": {
                "zim_fetch": {
                    "enabled": True,
                    "default_url": "https://example.test/x.zim",
                    "filename": "wikipedia_en_all_mini.zim",
                    "size_hint_bytes": 12_000_000_000,
                }
            },
        }
        assert should_auto_fetch_zim(manifest, target) is True


if __name__ == "__main__":
    test_knowledge_pack_searchable_by_users()
    test_should_auto_fetch_zim_respects_skip()
    test_download_resumes_with_http_range()
    test_zim_fetch_progress_roundtrip()
    test_fetch_zim_registers_kiwix()
    test_incomplete_zim_rejected_and_not_registered()
    test_should_auto_fetch_when_only_truncated_zim_present()
    print("OK test_wikipedia_zim_wiring")
