#!/usr/bin/env python3
"""Tests for maps.reindex, knowledge.index, and Kiwix ZIM registration."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "atlas-content-manager" / "usr" / "lib" / "atlas"))

os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"

from content_manager import (  # noqa: E402
    build_pack,
    install_pack,
    register_zim_with_kiwix,
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


def test_maps_reindex_updates_registry():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        atlas = td_path / "atlas"
        stage = td_path / "stage"
        manifest = {
            "schema": "atlas.pack/v1",
            "id": "atlas.maps.uk",
            "version": "2026.07",
            "type": "atlas.content.map",
            "name": "United Kingdom Offline Maps",
            "description": "test",
            "size_bytes": 100,
            "minimum_os_version": "0.1.0",
            "architectures": ["all"],
            "mount_target": str(atlas / "maps" / "uk"),
            "licences": ["ODbL"],
            "sources": [],
            "dependencies": [],
            "conflicts": [],
            "post_install_workflow": "maps.reindex",
            "meta": {"country": "uk", "bbox": [0, 0, 1, 1], "center": [0.5, 0.5]},
            "digest": "sha256:" + ("0" * 64),
        }
        _stage_pack(stage, manifest, {"README.txt": "UK maps", "meta.json": "{}"})
        pack = td_path / "uk.atlas-pack"
        digest = build_pack(stage, pack)
        m = json.loads((stage / "manifest.json").read_text(encoding="utf-8"))
        m["digest"] = digest
        (stage / "manifest.json").write_text(json.dumps(m), encoding="utf-8")
        build_pack(stage, pack)

        result = install_pack(pack, atlas)
        assert result["ok"]
        index = json.loads((atlas / "maps" / "uk" / "index.json").read_text(encoding="utf-8"))
        assert index["country"] == "uk"
        assert index["status"] == "stub"
        registry = json.loads((atlas / "maps" / "countries.json").read_text(encoding="utf-8"))
        assert "uk" in registry["countries"]


def test_knowledge_index_ingests_markdown_and_registers_zim():
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
            "meta": {"language": "eng", "kind": "wikipedia"},
            "digest": "sha256:" + ("0" * 64),
        }
        _stage_pack(
            stage,
            manifest,
            {
                "articles/Solar_System.md": "# Solar System\nThe Sun and planets.",
                "sample.zim": "FAKE-ZIM-BYTES-FOR-TEST",
            },
        )
        # .zim written as text is fine for registration copy test
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
        assert marker["ingested_docs"] >= 1
        assert "sample.zim" in marker["zim_books"]
        assert (atlas / "kiwix" / "sample.zim").is_file()
        lib = (atlas / "kiwix" / "library.xml").read_text(encoding="utf-8")
        assert "sample.zim" in lib


def test_register_zim_with_kiwix_idempotent():
    with tempfile.TemporaryDirectory() as td:
        atlas = Path(td) / "atlas"
        zim = Path(td) / "book.zim"
        zim.write_bytes(b"zim")
        register_zim_with_kiwix(zim, atlas, title="Book", language="eng")
        register_zim_with_kiwix(zim, atlas, title="Book", language="eng")
        lib = (atlas / "kiwix" / "library.xml").read_text(encoding="utf-8")
        assert lib.count('path="book.zim"') == 1


def test_kids_education_pack_installs():
    kids = ROOT / "dist" / "packs" / "atlas-education-kids-home.atlas-pack"
    if not kids.is_file():
        print("SKIP test_kids_education_pack_installs (pack not built)")
        return
    with tempfile.TemporaryDirectory() as td:
        atlas = Path(td) / "atlas"
        # Override mount_target by installing — pack has absolute /srv/atlas path.
        # Install still works: _resolve_target may place under content-packs if outside atlas root.
        result = install_pack(kids, atlas)
        assert result["ok"]
        assert result["id"] == "atlas.education.kids-home"


if __name__ == "__main__":
    test_maps_reindex_updates_registry()
    print("OK maps.reindex")
    test_knowledge_index_ingests_markdown_and_registers_zim()
    print("OK knowledge.index + zim")
    test_register_zim_with_kiwix_idempotent()
    print("OK zim register")
    test_kids_education_pack_installs()
    print("OK kids pack")
    print("OK test_content_pack_workflows")
