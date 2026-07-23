#!/usr/bin/env python3
"""Content pack install, compat checks, rollback, and uninstall."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "atlas-content-manager" / "usr" / "lib" / "atlas"))

from content_manager import (  # noqa: E402
    PackError,
    build_pack,
    check_compatibility,
    install_pack,
    load_installed,
    uninstall_pack,
    verify_checksums,
)


def _stage_maps_pack(stage: Path, *, mount_target: str, minimum_os: str = "0.1.0") -> Path:
    (stage / "payload").mkdir(parents=True)
    (stage / "payload" / "tile.txt").write_text("stub tile", encoding="utf-8")
    (stage / "licences").mkdir()
    (stage / "licences" / "ODbL.txt").write_text("ODbL", encoding="utf-8")
    manifest = {
        "schema": "atlas.pack/v1",
        "id": "atlas.maps.uk.test",
        "version": "1.0.0",
        "type": "atlas.content.map",
        "name": "Test Maps",
        "description": "Unit test pack",
        "size_bytes": 4096,
        "minimum_os_version": minimum_os,
        "architectures": ["all"],
        "mount_target": mount_target,
        "licences": ["ODbL-1.0"],
        "sources": [],
        "dependencies": [],
        "conflicts": [],
        "post_install_workflow": "maps.reindex",
        "digest": "sha256:" + "0" * 64,
    }
    (stage / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    out = stage.parent / "test.atlas-pack"
    os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
    digest = build_pack(stage, out)
    manifest["digest"] = digest
    (stage / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    build_pack(stage, out)
    return out


def test_install_and_uninstall():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        atlas = td_path / "srv"
        stage = td_path / "stage"
        stage.mkdir()
        target = str(atlas / "maps" / "uk-test")
        pack = _stage_maps_pack(stage, mount_target=target)
        result = install_pack(pack, atlas)
        assert result["ok"]
        assert result["id"] == "atlas.maps.uk.test"
        assert (Path(target) / "tile.txt").is_file()
        assert (Path(target) / ".atlas-indexed").is_file()
        inst = load_installed(atlas)
        assert any(p["id"] == "atlas.maps.uk.test" for p in inst["packs"])
        uninstall_pack("atlas.maps.uk.test", atlas)
        assert not Path(target).exists()
        assert not any(p["id"] == "atlas.maps.uk.test" for p in load_installed(atlas)["packs"])


def test_compat_rejects_high_os_version():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        atlas = td_path / "srv"
        atlas.mkdir()
        stage = td_path / "stage"
        stage.mkdir()
        manifest = {
            "schema": "atlas.pack/v1",
            "id": "atlas.future",
            "version": "9.0.0",
            "type": "atlas.content.map",
            "name": "Future",
            "description": "Needs newer OS",
            "size_bytes": 1024,
            "minimum_os_version": "99.0.0",
            "architectures": ["all"],
            "mount_target": str(atlas / "maps" / "future"),
            "licences": [],
            "sources": [],
            "dependencies": [],
            "conflicts": [],
            "digest": "sha256:" + "0" * 64,
        }
        compat = check_compatibility(manifest, atlas)
        assert not compat["ok"]
        assert any("Atlas OS" in e for e in compat["errors"])


def test_checksum_mismatch_raises():
    with tempfile.TemporaryDirectory() as td:
        stage = Path(td) / "stage"
        (stage / "payload").mkdir(parents=True)
        (stage / "payload" / "a.txt").write_text("a", encoding="utf-8")
        (stage / "licences").mkdir()
        (stage / "manifest.json").write_text("{}", encoding="utf-8")
        (stage / "checksums.sha256").write_text("deadbeef  payload/a.txt\n", encoding="utf-8")
        try:
            verify_checksums(stage)
            raise AssertionError("expected PackError")
        except PackError as e:
            assert "mismatch" in str(e).lower() or "checksum" in str(e).lower()


def test_rollback_on_workflow_failure():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        atlas = td_path / "srv"
        stage = td_path / "stage"
        stage.mkdir()
        target = str(atlas / "maps" / "bad")
        pack = _stage_maps_pack(stage, mount_target=target)

        def boom(_manifest, _target, _atlas_root):
            raise PackError("workflow_failed")

        try:
            install_pack(pack, atlas, hooks={"maps.reindex": boom})
            raise AssertionError("expected PackError")
        except PackError as e:
            assert "workflow_failed" in str(e)
        assert not Path(target).exists()


def _stage_knowledge_zim_pack(stage: Path, *, pack_id: str, mount_target: str, size_hint: int) -> Path:
    (stage / "payload").mkdir(parents=True)
    (stage / "payload" / "README.md").write_text("Knowledge stub\n", encoding="utf-8")
    (stage / "licences").mkdir()
    (stage / "licences" / "CC-BY-SA-4.0.txt").write_text("CC-BY-SA", encoding="utf-8")
    slug = pack_id.rsplit(".", 1)[-1]
    manifest = {
        "schema": "atlas.pack/v1",
        "id": pack_id,
        "version": "1.0.0",
        "type": "atlas.content.knowledge",
        "name": "Test Wikipedia",
        "description": "Unit test knowledge pack",
        "size_bytes": 4096,
        "minimum_os_version": "0.1.0",
        "architectures": ["all"],
        "mount_target": mount_target,
        "licences": ["CC-BY-SA-4.0"],
        "sources": [],
        "dependencies": [],
        "conflicts": [],
        "post_install_workflow": "",
        "meta": {
            "language": "eng",
            "zim_fetch": {
                "enabled": True,
                "default_url": "https://example.test/wiki.zim",
                "filename": f"{slug}.zim",
                "size_hint_bytes": size_hint,
            },
        },
        "digest": "sha256:" + "0" * 64,
    }
    (stage / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    out = stage.parent / f"{slug}.atlas-pack"
    os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
    digest = build_pack(stage, out)
    manifest["digest"] = digest
    (stage / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    build_pack(stage, out)
    return out


def test_zim_fetch_progress_fields_and_async_install_flag():
    from content_manager import (
        _pack_slug,
        read_zim_fetch_progress,
        should_auto_fetch_zim,
        write_zim_fetch_progress,
    )

    with tempfile.TemporaryDirectory() as td:
        atlas = Path(td) / "srv"
        write_zim_fetch_progress(
            atlas,
            {
                "pack_slug": "wikipedia-en-mini",
                "status": "downloading",
                "done": False,
                "downloaded": 50,
                "total": 200,
                "message": "Downloading…",
            },
            "wikipedia-en-mini",
        )
        st = read_zim_fetch_progress(atlas, "wikipedia-en-mini")
        assert st["status"] == "downloading"
        assert st["downloaded"] == 50
        assert st["total"] == 200
        assert st["percent"] == 25.0
        assert st["done"] is False
        assert "updated_at" in st

        stage = Path(td) / "stage"
        stage.mkdir()
        target = str(atlas / "knowledge" / "packs" / "wikipedia-en-mini")
        pack = _stage_knowledge_zim_pack(
            stage,
            pack_id="atlas.knowledge.wikipedia-en-mini",
            mount_target=target,
            size_hint=12_000_000_000,
        )
        # Skip network fetch during install; Command Centre starts async itself.
        result = install_pack(pack, atlas, fetch_tiles=False)
        assert result["ok"]
        manifest = json.loads((Path(target) / "manifest.json").read_text(encoding="utf-8"))
        assert should_auto_fetch_zim(manifest, Path(target)) is True
        assert _pack_slug(manifest, Path(target)) == "wikipedia-en-mini"
        # Pending until async worker runs (CC path).
        assert result.get("zim_status") in {None, "pending"}


if __name__ == "__main__":
    test_install_and_uninstall()
    test_compat_rejects_high_os_version()
    test_checksum_mismatch_raises()
    test_rollback_on_workflow_failure()
    test_zim_fetch_progress_fields_and_async_install_flag()
    print("OK test_content_install")
