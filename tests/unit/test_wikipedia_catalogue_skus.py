#!/usr/bin/env python3
"""Wikipedia catalogue SKUs: starter + mini/nopic/maxi with locked ZIM URLs."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "atlas-content-manager" / "usr" / "lib" / "atlas"))

os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
os.environ["ATLAS_ZIM_SKIP_FETCH"] = "1"

from content_manager import (  # noqa: E402
    build_pack,
    fetch_zim_for_manifest,
    install_pack,
    load_catalogue,
)

CATALOGUE = ROOT / "content" / "catalogues" / "catalogue.json"

EXPECTED = {
    "atlas.knowledge.wikipedia-en": {
        "size_class": "small",
        "url": "https://download.kiwix.org/zim/wikipedia/wikipedia_en_100_nopic_2026-04.zim",
        "filename": "wikipedia_en_100_nopic.zim",
        "size_hint_bytes": 14_000_000,
    },
    "atlas.knowledge.wikipedia-en-mini": {
        "size_class": "large",
        "url": "https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_mini_2026-06.zim",
        "filename": "wikipedia_en_all_mini.zim",
        "size_hint_bytes": 12_000_000_000,
    },
    "atlas.knowledge.wikipedia-en-nopic": {
        "size_class": "large",
        "url": "https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_nopic_2026-06.zim",
        "filename": "wikipedia_en_all_nopic.zim",
        "size_hint_bytes": 49_000_000_000,
    },
    "atlas.knowledge.wikipedia-en-maxi": {
        "size_class": "large",
        "url": "https://download.kiwix.org/zim/wikipedia/wikipedia_en_all_maxi_2026-02.zim",
        "filename": "wikipedia_en_all_maxi.zim",
        "size_hint_bytes": 115_000_000_000,
    },
}


def test_catalogue_has_wikipedia_skus():
    cat = load_catalogue(CATALOGUE)
    packs = cat.get("packs") or []
    by_id = {p["id"]: p for p in packs}
    for pack_id, expect in EXPECTED.items():
        assert pack_id in by_id, f"missing catalogue id {pack_id}"
        entry = by_id[pack_id]
        assert entry.get("category") == "knowledge"
        assert entry.get("size_class") == expect["size_class"]
        assert entry.get("size_hint_bytes") == expect["size_hint_bytes"]
        zim = entry.get("zim_fetch") or {}
        assert zim.get("default_url") == expect["url"]
        assert zim.get("filename") == expect["filename"]
        if expect["size_class"] == "large":
            assert entry.get("size_warning"), f"{pack_id} needs size_warning"
            assert entry.get("download_on_install") is True
        else:
            assert entry.get("size_class") == "small"


def test_large_sku_fetch_uses_locked_url():
    """Mock download: mini SKU must pull all_mini URL, not starter en_100."""
    with tempfile.TemporaryDirectory() as td:
        atlas = Path(td) / "srv"
        target = atlas / "knowledge" / "packs" / "wikipedia-en-mini"
        target.mkdir(parents=True)
        url = EXPECTED["atlas.knowledge.wikipedia-en-mini"]["url"]
        manifest = {
            "id": "atlas.knowledge.wikipedia-en-mini",
            "name": "Wikipedia EN mini",
            "description": "test",
            "type": "atlas.content.knowledge",
            "meta": {
                "language": "eng",
                "variant": "mini",
                "size_class": "large",
                "size_hint_bytes": 12_000_000_000,
                "zim_fetch": {
                    "enabled": True,
                    "default_url": url,
                    "filename": "wikipedia_en_all_mini.zim",
                    "size_hint_bytes": 12_000_000_000,
                },
            },
        }
        seen: dict[str, str] = {}

        def fake_download(fetch_url, dest, progress_cb=None):
            seen["url"] = fetch_url
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(b"FAKE-MINI-ZIM")
            if progress_cb:
                progress_cb(13, 13)

        os.environ.pop("ATLAS_ZIM_URL", None)
        os.environ.pop("ATLAS_ZIM_SKIP_FETCH", None)
        with mock.patch("content_manager._http_head_ok", return_value=True), mock.patch(
            "content_manager._download_url_to_file", side_effect=fake_download
        ):
            info = fetch_zim_for_manifest(manifest, target, atlas)
        assert info["ok"]
        assert seen["url"] == url
        assert (target / "wikipedia_en_all_mini.zim").is_file()
        assert (atlas / "kiwix" / "wikipedia_en_all_mini.zim").is_file()


def test_large_sku_pack_install_skips_network_when_env_set():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        atlas = td_path / "srv"
        stage = td_path / "stage"
        stage.mkdir()
        (stage / "payload").mkdir()
        (stage / "payload" / "README.md").write_text("# mini stub\n", encoding="utf-8")
        (stage / "licences").mkdir()
        (stage / "licences" / "CC.txt").write_text("cc", encoding="utf-8")
        mount = str(atlas / "knowledge" / "packs" / "wikipedia-en-mini")
        manifest = {
            "schema": "atlas.pack/v1",
            "id": "atlas.knowledge.wikipedia-en-mini",
            "version": "1.0.0",
            "type": "atlas.content.knowledge",
            "name": "Wikipedia EN mini",
            "description": "stub",
            "size_bytes": 4096,
            "minimum_os_version": "0.1.0",
            "architectures": ["all"],
            "mount_target": mount,
            "licences": ["CC-BY-SA-4.0"],
            "sources": [],
            "dependencies": [],
            "conflicts": [
                "atlas.knowledge.wikipedia-en-nopic",
                "atlas.knowledge.wikipedia-en-maxi",
            ],
            "post_install_workflow": "knowledge.index",
            "meta": {
                "language": "eng",
                "kind": "wikipedia",
                "variant": "mini",
                "size_class": "large",
                "zim_fetch": {
                    "enabled": True,
                    "default_url": EXPECTED["atlas.knowledge.wikipedia-en-mini"]["url"],
                    "filename": "wikipedia_en_all_mini.zim",
                    "size_hint_bytes": 12_000_000_000,
                },
            },
            "digest": "sha256:" + "0" * 64,
        }
        (stage / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        out = td_path / "mini.atlas-pack"
        digest = build_pack(stage, out)
        manifest["digest"] = digest
        (stage / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        build_pack(stage, out)
        os.environ["ATLAS_ZIM_SKIP_FETCH"] = "1"
        result = install_pack(out, atlas, fetch_tiles=False)
        assert result["ok"]
        assert result["id"] == "atlas.knowledge.wikipedia-en-mini"
        assert not list(Path(mount).rglob("*.zim"))


if __name__ == "__main__":
    test_catalogue_has_wikipedia_skus()
    test_large_sku_fetch_uses_locked_url()
    test_large_sku_pack_install_skips_network_when_env_set()
    print("OK test_wikipedia_catalogue_skus")
