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
    _zim_rag_config,
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
        assert (target / ".atlas-zim-rag.json").is_file()
        marker = json.loads((target / ".atlas-zim-rag.json").read_text(encoding="utf-8"))
        assert int(marker.get("extracted") or 0) >= 1


def test_extract_zim_html_articles_uses_zimdump_mock():
    with tempfile.TemporaryDirectory() as td:
        zim = Path(td) / "sample.zim"
        zim.write_bytes(b"FAKE-ZIM")
        out = Path(td) / "extracted"
        list_calls = []

        def fake_run(cmd, **kwargs):
            class R:
                returncode = 0
                stdout = b""
                stderr = b""

            if cmd[1] == "list":
                list_calls.append(cmd)
                r = R()
                r.stdout = "path: A/Should_Not_Be_Used\n"
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
            info = extract_zim_html_articles(
                zim, out, max_articles=2, allowlist=["Gravity", "Water"]
            )
        assert info["ok"]
        assert info["backend"] == "zimdump"
        assert info["mode"] == "seed_titles"
        assert info["extracted"] == 2
        assert list_calls == [], "zimdump list must never run for Index-for-agents RAG"
        assert list(out.glob("*.html"))


def test_extract_never_calls_zimdump_list_even_when_seeds_miss():
    with tempfile.TemporaryDirectory() as td:
        zim = Path(td) / "sample.zim"
        zim.write_bytes(b"FAKE-ZIM")
        out = Path(td) / "extracted"
        list_calls = []

        def fake_run(cmd, **kwargs):
            class R:
                returncode = 1
                stdout = b""
                stderr = b"missing"

            if cmd[1] == "list":
                list_calls.append(cmd)
                return R()
            return R()

        with mock.patch("content_manager.shutil.which", return_value="/usr/bin/zimdump"), mock.patch(
            "content_manager.subprocess.run", side_effect=fake_run
        ), mock.patch(
            "content_manager._extract_zim_via_libzim",
            return_value={"ok": False, "backend": "libzim", "extracted": 0, "error": "no_libzim"},
        ):
            info = extract_zim_html_articles(
                zim, out, max_articles=5, allowlist=["Missing_Page_XYZ"]
            )
        assert list_calls == []
        assert int(info.get("extracted") or 0) == 0


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

        # Control / marker files must exist on disk but never enter the searchable index.
        pack_dir = atlas / "knowledge" / "packs" / "wikipedia-en"
        assert (pack_dir / "manifest.json").is_file()
        from knowledge_service import KnowledgeService

        ks = KnowledgeService(atlas / "knowledge", keyword_only=True)
        ctrl_hits = ks.search("alice", "post_install_workflow size_class atlas-zim-rag extracted 0")
        assert all(
            (h.get("name") or "") not in {"manifest.json", ".atlas-zim-rag.json"}
            for h in ctrl_hits
        )
        assert ks.search("alice", "Solar System planets") or ks.search("alice", "Gravity Attraction")


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


def test_zim_rag_defaults_on_for_zim_fetch_packs():
    cfg = _zim_rag_config(
        {
            "id": "atlas.knowledge.medicine-en",
            "meta": {
                "zim_fetch": {
                    "enabled": True,
                    "default_url": "https://example.test/med.zim",
                    "filename": "med.zim",
                }
            },
        }
    )
    assert cfg.get("enabled") is True
    assert int(cfg.get("max_articles") or 0) > 0
    assert "Eiffel_Tower" in (cfg.get("allowlist") or [])
    explicit = _zim_rag_config({"meta": {"zim_rag": {"enabled": True, "max_articles": 5}}})
    assert "Eiffel_Tower" in (explicit.get("allowlist") or [])
    custom = _zim_rag_config({"meta": {"zim_rag": {"enabled": True, "allowlist": ["Only_This"]}}})
    assert custom.get("allowlist") == ["Only_This"]
    empty = _zim_rag_config({"meta": {"zim_rag": {"enabled": True, "allowlist": []}}})
    assert "Eiffel_Tower" in (empty.get("allowlist") or [])
    assert int(empty.get("max_articles") or 0) <= 100
    assert _zim_rag_config({"meta": {"zim_rag": {"enabled": False}}}).get("enabled") is False
    assert _zim_rag_config({"meta": {}}) == {}


def test_extract_prefers_seed_titles_via_zimdump():
    with tempfile.TemporaryDirectory() as td:
        zim = Path(td) / "sample.zim"
        zim.write_bytes(b"FAKE-ZIM")
        out = Path(td) / "extracted"
        list_calls = []

        def fake_run(cmd, **kwargs):
            class R:
                returncode = 0
                stdout = b""
                stderr = b""

            if cmd[1] == "list":
                list_calls.append(cmd)
                r = R()
                r.stdout = "path: A/Unrelated\n"
                return r
            if cmd[1] == "show":
                r = R()
                url = cmd[2].split("=", 1)[-1]
                if "Eiffel" in url:
                    r.stdout = b"<html><body><h1>Eiffel Tower</h1><p>Paris landmark.</p></body></html>"
                else:
                    r.returncode = 1
                    r.stdout = b""
                return r
            return R()

        with mock.patch("content_manager.shutil.which", return_value="/usr/bin/zimdump"), mock.patch(
            "content_manager.subprocess.run", side_effect=fake_run
        ):
            info = extract_zim_html_articles(
                zim, out, max_articles=5, allowlist=["Eiffel_Tower", "Missing_Page"]
            )
        assert info["ok"]
        assert info["extracted"] >= 1
        assert list_calls == []
        assert any("Eiffel" in p.name for p in out.glob("*.html"))


def test_no_zim_found_writes_root_marker():
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "pack"
        target.mkdir()
        atlas = Path(td) / "atlas"
        (atlas / "kiwix").mkdir(parents=True)
        manifest = {
            "id": "atlas.knowledge.wikipedia-en-mini",
            "name": "Wiki mini",
            "meta": {
                "zim_rag": {"enabled": True, "max_articles": 5},
                "zim_fetch": {"filename": "wikipedia_en_all_mini.zim"},
            },
        }
        info = maybe_extract_zim_html_for_rag(manifest, target, atlas)
        assert info is not None
        assert not info.get("ok")
        assert "no_zim_found" in str(info.get("error") or "")
        assert (target / ".atlas-zim-rag.json").is_file()


def test_finds_zim_in_kiwix_library():
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "pack"
        target.mkdir()
        atlas = Path(td) / "atlas"
        zim = atlas / "kiwix" / "wikipedia_en_all_mini.zim"
        zim.parent.mkdir(parents=True)
        zim.write_bytes(b"FAKE-ZIM")
        list_calls = []

        def fake_run(cmd, **kwargs):
            class R:
                returncode = 0
                stdout = b""
                stderr = b""

            if cmd[1] == "list":
                list_calls.append(cmd)
                r = R()
                r.stdout = "path: A/Gravity\n"
                return r
            if cmd[1] == "show":
                r = R()
                r.stdout = b"<html><body><h1>Gravity</h1></body></html>"
                return r
            return R()

        manifest = {
            "id": "atlas.knowledge.wikipedia-en-mini",
            "meta": {
                "zim_rag": {"enabled": True, "max_articles": 2, "allowlist": ["Gravity"]},
                "zim_fetch": {"filename": "wikipedia_en_all_mini.zim"},
            },
        }
        with mock.patch("content_manager.shutil.which", return_value="/usr/bin/zimdump"), mock.patch(
            "content_manager.subprocess.run", side_effect=fake_run
        ):
            info = maybe_extract_zim_html_for_rag(manifest, target, atlas)
        assert info and info.get("ok")
        assert int(info.get("extracted") or 0) >= 1
        assert list_calls == []
        assert (target / ".atlas-zim-rag.json").is_file()
        assert (target / "extracted" / ".atlas-zim-rag.json").is_file()


if __name__ == "__main__":
    test_rag_html_seed_extract_without_zimdump()
    test_extract_zim_html_articles_uses_zimdump_mock()
    test_extract_never_calls_zimdump_list_even_when_seeds_miss()
    test_extract_prefers_seed_titles_via_zimdump()
    test_knowledge_index_ingests_extracted_html()
    test_kolibri_prepare_writes_channel_lock()
    test_expand_resolves_file_url()
    test_zim_rag_defaults_on_for_zim_fetch_packs()
    test_no_zim_found_writes_root_marker()
    test_finds_zim_in_kiwix_library()
    print("OK test_zim_rag_and_education")
