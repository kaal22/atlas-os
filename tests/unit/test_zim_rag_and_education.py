#!/usr/bin/env python3
"""Tests for selective ZIM HTML → agent RAG extract path."""
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

from content_manager import (  # noqa: E402
    build_pack,
    extract_zim_html_articles,
    install_pack,
    maybe_extract_zim_html_for_rag,
)


def _stage_pack(stage: Path, manifest: dict, files: dict[str, str]) -> None:
    (stage / "payload").mkdir(parents=True)
    (stage / "licences").mkdir(parents=True)
    (stage / "attribution").mkdir(parents=True)
    (stage / "licences" / "LICENCE.txt").write_text("test licence", encoding="utf-8")
    (stage / "attribution" / "ATTR.txt").write_text("test attr", encoding="utf-8")
    for rel, text in files.items():
        path = stage / "payload" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (stage / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def test_rag_html_seed_extract_without_zimdump():
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "pack"
        (target / "rag-html").mkdir(parents=True)
        (target / "rag-html" / "Solar_System.html").write_text(
            "<html><body><h1>Solar System</h1><p>The Sun and planets.</p></body></html>",
            encoding="utf-8",
        )
        manifest = {
            "id": "atlas.knowledge.wikipedia-en",
            "name": "Wiki starter",
            "meta": {"zim_rag": {"enabled": True, "max_articles": 10}},
        }
        info = maybe_extract_zim_html_for_rag(manifest, target, Path(td) / "atlas")
        assert info is not None
        assert info.get("ok")
        assert int(info.get("extracted") or 0) >= 1
        assert (target / "extracted" / "Solar_System.html").is_file()


def test_extract_zim_html_articles_uses_zimdump_mock():
    with tempfile.TemporaryDirectory() as td:
        zim = Path(td) / "sample.zim"
        zim.write_bytes(b"FAKE-ZIM")
        out = Path(td) / "extracted"

        def fake_run(cmd, **kwargs):
            class R:
                returncode = 0
                stdout = b""
                stderr = b""

            if cmd[1] == "list":
                r = R()
                r.stdout = "path: A/Gravity\npath: A/Water_cycle\n"
                return r
            if cmd[1] == "show":
                r = R()
                title = cmd[2].split("=", 1)[-1]
                r.stdout = f"<html><body><h1>{title}</h1></body></html>".encode()
                return r
            return R()

        with mock.patch("content_manager.shutil.which", return_value="/usr/bin/zimdump"), mock.patch(
            "content_manager.subprocess.run", side_effect=fake_run
        ):
            info = extract_zim_html_articles(zim, out, max_articles=2)
        assert info["ok"]
        assert info["backend"] == "zimdump"
        assert info["extracted"] == 2
        assert list(out.glob("*.html"))


def test_knowledge_index_ingests_extracted_html():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        atlas = td_path / "atlas"
        stage = td_path / "stage"
        manifest = {
            "schema": "atlas.pack/v1",
            "id": "atlas.knowledge.wikipedia-en",
            "version": "2026.07",
            "type": "atlas.content.knowledge",
            "name": "Wikipedia curated",
            "description": "test wiki",
            "size_bytes": 100,
            "minimum_os_version": "0.1.0",
            "architectures": ["all"],
            "mount_target": str(atlas / "knowledge" / "packs" / "wikipedia-en"),
            "licences": ["CC-BY-SA-4.0"],
            "sources": ["wikipedia"],
            "dependencies": [],
            "conflicts": [],
            "post_install_workflow": "knowledge.index",
            "meta": {
                "language": "eng",
                "kind": "wikipedia",
                "zim_rag": {"enabled": True, "max_articles": 5},
            },
            "digest": "sha256:" + ("0" * 64),
        }
        _stage_pack(
            stage,
            manifest,
            {
                "articles/Solar_System.md": "# Solar System\nThe Sun and planets.",
                "rag-html/Gravity.html": "<html><body><h1>Gravity</h1><p>Attraction.</p></body></html>",
            },
        )
        pack = td_path / "wiki.atlas-pack"
        digest = build_pack(stage, pack)
        m = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
        m["digest"] = digest
        (stage / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
        build_pack(stage, pack)

        result = install_pack(pack, atlas)
        assert result["ok"]
        marker = json.loads(
            (atlas / "knowledge" / "packs" / "wikipedia-en" / ".atlas-indexed").read_text(encoding="utf-8")
        )
        assert marker.get("ingested_docs", 0) >= 2
        zim_rag = marker.get("zim_rag") or {}
        assert int(zim_rag.get("extracted") or 0) >= 1
        assert (atlas / "knowledge" / "packs" / "wikipedia-en" / "extracted" / "Gravity.html").is_file()


def test_kolibri_prepare_writes_channel_lock():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        atlas = td_path / "atlas"
        stage = td_path / "stage"
        channel_id = "378cf4128c854c2795c100b5aca7a3ed"
        manifest = {
            "schema": "atlas.pack/v1",
            "id": "atlas.education.kolibri-home-learning",
            "version": "2026.07",
            "type": "atlas.content.education",
            "name": "Inclusive Home Learning Activities",
            "description": "test",
            "size_bytes": 100,
            "minimum_os_version": "0.1.0",
            "architectures": ["all"],
            "mount_target": str(atlas / "kolibri" / "channels" / "kolibri-home-learning"),
            "licences": ["test"],
            "sources": [],
            "dependencies": [],
            "conflicts": [],
            "post_install_workflow": "education.kolibri_prepare",
            "meta": {
                "kolibri_channel": {
                    "channel_id": channel_id,
                    "name": "Inclusive Home Learning Activities",
                    "redistribution": "operator_may_import_not_bundled",
                    "licence_note": "test",
                }
            },
            "digest": "sha256:" + ("0" * 64),
        }
        _stage_pack(stage, manifest, {"README.txt": "kolibri channel stub"})
        pack = td_path / "kolibri.atlas-pack"
        digest = build_pack(stage, pack)
        m = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
        m["digest"] = digest
        (stage / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
        build_pack(stage, pack)

        result = install_pack(pack, atlas)
        assert result["ok"]
        lock = json.loads(
            (atlas / "kolibri" / "channels" / "kolibri-home-learning" / "channel.lock.json").read_text(
                encoding="utf-8"
            )
        )
        assert lock["channel_id"] == channel_id
        assert (atlas / "kolibri" / "channels" / f"{channel_id}.lock.json").is_file()


def test_expand_resolves_file_url(tmp_path: Path | None = None):
    from content_manager import resolve_expand_fetch_url

    with tempfile.TemporaryDirectory() as td:
        tgz = Path(td) / "kids-home-learning-expand.tar.gz"
        tgz.write_bytes(b"fake-tarball")
        url = resolve_expand_fetch_url(
            {"url": f"file://{tgz}", "fallback_url": "https://example.test/expand.tar.gz"}
        )
        assert url.startswith("file:")
        assert "kids-home-learning-expand.tar.gz" in url


if __name__ == "__main__":
    test_rag_html_seed_extract_without_zimdump()
    test_extract_zim_html_articles_uses_zimdump_mock()
    test_knowledge_index_ingests_extracted_html()
    test_kolibri_prepare_writes_channel_lock()
    test_expand_resolves_file_url()
    print("OK test_zim_rag_and_education")
