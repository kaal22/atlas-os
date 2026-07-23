#!/usr/bin/env python3
"""Wikipedia ZIM fetch helpers + knowledge pack ingest for agents."""
from __future__ import annotations

import json
import os
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
    build_pack,
    fetch_zim_for_manifest,
    install_pack,
    should_auto_fetch_zim,
    write_zim_fetch_progress,
    read_zim_fetch_progress,
)
from knowledge_service import KnowledgeService  # noqa: E402


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
        (target / "already.zim").write_bytes(b"zim")
        assert should_auto_fetch_zim(manifest, target) is False


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
                    "size_hint_bytes": 12,
                },
            },
        }

        def fake_download(url, dest, progress_cb=None):
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"FAKEZIMDATA!!")
            if progress_cb:
                progress_cb(len(b"FAKEZIMDATA!!"), len(b"FAKEZIMDATA!!"))

        with mock.patch("content_manager._http_head_ok", return_value=True), mock.patch(
            "content_manager._download_url_to_file", side_effect=fake_download
        ):
            info = fetch_zim_for_manifest(manifest, target, atlas)
        assert info["ok"]
        assert (target / "wiki.zim").is_file()
        assert (atlas / "kiwix" / "wiki.zim").is_file()
        assert (atlas / "kiwix" / "library.xml").is_file()
        st = read_zim_fetch_progress(atlas, "wikipedia-en")
        assert st["status"] == "ready" and st["done"] is True


if __name__ == "__main__":
    test_knowledge_pack_searchable_by_users()
    test_should_auto_fetch_zim_respects_skip()
    test_zim_fetch_progress_roundtrip()
    test_fetch_zim_registers_kiwix()
    print("OK test_wikipedia_zim_wiring")
