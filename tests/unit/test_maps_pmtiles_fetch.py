#!/usr/bin/env python3
"""Tests for online country PMTiles fetch helpers."""
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
os.environ["ATLAS_MAPS_SKIP_FETCH"] = "1"  # never hit network in default install tests

from content_manager import (  # noqa: E402
    MIN_USABLE_PMTILES_BYTES,
    PackError,
    build_pack,
    fetch_country_pmtiles,
    fetch_map_tiles_for_manifest,
    has_usable_map_tiles,
    install_pack,
    make_minimal_pmtiles,
    should_auto_fetch_map_tiles,
)


def test_should_auto_fetch_requires_tiles_fetch_meta():
    target = Path("/tmp/does-not-matter")
    bare = {"type": "atlas.content.map", "meta": {"country": "uk", "bbox": [0, 0, 1, 1]}}
    assert should_auto_fetch_map_tiles(bare, target) is False
    with_fetch = {
        "type": "atlas.content.map",
        "meta": {
            "country": "uk",
            "bbox": [0, 0, 1, 1],
            "tiles_fetch": {"enabled": True, "mode": "protomaps_extract"},
        },
    }
    # Skip-fetch env is set for this module — expect False
    assert should_auto_fetch_map_tiles(with_fetch, target) is False
    os.environ.pop("ATLAS_MAPS_SKIP_FETCH", None)
    try:
        assert should_auto_fetch_map_tiles(with_fetch, target) is True
    finally:
        os.environ["ATLAS_MAPS_SKIP_FETCH"] = "1"


def test_tiny_pmtiles_not_usable_still_wants_fetch(tmp_path: Path | None = None):
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "uk"
        target.mkdir()
        (target / "uk.pmtiles").write_bytes(b"tiny")
        assert has_usable_map_tiles(target) is False
        with_fetch = {
            "type": "atlas.content.map",
            "meta": {
                "country": "uk",
                "bbox": [-8, 49, 2, 61],
                "tiles_fetch": {"enabled": True, "mode": "protomaps_extract"},
            },
        }
        os.environ.pop("ATLAS_MAPS_SKIP_FETCH", None)
        try:
            assert should_auto_fetch_map_tiles(with_fetch, target) is True
        finally:
            os.environ["ATLAS_MAPS_SKIP_FETCH"] = "1"


def test_fetch_country_pmtiles_direct_url(tmp_path: Path | None = None):
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        dest = td_path / "maps" / "ie"
        atlas = td_path / "atlas"
        fake_bytes = make_minimal_pmtiles(MIN_USABLE_PMTILES_BYTES)

        class _Resp:
            headers = {"Content-Length": str(len(fake_bytes))}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, n: int = -1):
                if not hasattr(self, "_sent"):
                    self._sent = True
                    return fake_bytes
                return b""

        with mock.patch("content_manager.urllib.request.urlopen", return_value=_Resp()):
            out = fetch_country_pmtiles(
                dest,
                country="ie",
                bbox=[-10.7, 51.4, -5.9, 55.4],
                direct_url="https://example.test/ie.pmtiles",
                atlas_root=atlas,
                size_hint_bytes=len(fake_bytes),
            )
        assert out.is_file()
        assert out.read_bytes() == fake_bytes
        progress = json.loads((atlas / "maps" / ".fetch-progress-ie").read_text(encoding="utf-8"))
        # Direct fetch leaves finalizing; ready comes after reindex via fetch_map_tiles_for_manifest.
        assert progress["done"] is False
        assert progress["status"] == "finalizing"


def test_fetch_country_pmtiles_rejects_tiny_download():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        dest = td_path / "maps" / "ie"
        atlas = td_path / "atlas"
        fake_bytes = b"tiny"

        class _Resp:
            headers = {"Content-Length": str(len(fake_bytes))}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, n: int = -1):
                if not hasattr(self, "_sent"):
                    self._sent = True
                    return fake_bytes
                return b""

        with mock.patch("content_manager.urllib.request.urlopen", return_value=_Resp()):
            try:
                fetch_country_pmtiles(
                    dest,
                    country="ie",
                    bbox=[-10.7, 51.4, -5.9, 55.4],
                    direct_url="https://example.test/ie.pmtiles",
                    atlas_root=atlas,
                )
                raise AssertionError("expected PackError for tiny download")
            except PackError as e:
                assert "invalid" in str(e).lower() or "too small" in str(e).lower() or "magic" in str(e).lower()


def test_fetch_country_pmtiles_extract_invokes_cli():
    import io

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        dest = td_path / "maps" / "nl"
        atlas = td_path / "atlas"
        cli = td_path / "pmtiles"
        payload = make_minimal_pmtiles(MIN_USABLE_PMTILES_BYTES)
        cli.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        cli.chmod(0o755)

        def _fake_popen(cmd, **kwargs):
            partial = Path(cmd[3])
            partial.write_bytes(payload)
            proc = mock.Mock()
            proc.poll = mock.Mock(return_value=0)
            proc.returncode = 0
            proc.stdout = None
            proc.stderr = io.StringIO("")
            proc.kill = mock.Mock()
            proc.wait = mock.Mock(return_value=0)
            return proc

        with mock.patch("content_manager.ensure_pmtiles_cli", return_value=cli), mock.patch(
            "content_manager.resolve_protomaps_planet_url",
            return_value="https://build.protomaps.com/20260721.pmtiles",
        ), mock.patch("content_manager.subprocess.Popen", side_effect=_fake_popen):
            out = fetch_country_pmtiles(
                dest,
                country="nl",
                bbox=[3.3, 50.7, 7.3, 53.6],
                maxzoom=8,
                atlas_root=atlas,
                size_hint_bytes=80_000_000,
            )
        assert out.stat().st_size >= MIN_USABLE_PMTILES_BYTES
        assert has_usable_map_tiles(dest)
        prog = json.loads((atlas / "maps" / ".fetch-progress-nl").read_text(encoding="utf-8"))
        assert prog["status"] == "finalizing"
        assert prog["done"] is False
        # size_hint must not force percent/completion — actual size is smaller than hint
        assert prog["downloaded"] == out.stat().st_size
        assert prog["total"] == out.stat().st_size


def test_fetch_map_tiles_marks_ready_only_after_reindex():
    import io

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        atlas = td_path / "atlas"
        target = atlas / "maps" / "uk"
        target.mkdir(parents=True)
        payload = make_minimal_pmtiles(150_000)
        manifest = {
            "id": "atlas.maps.uk",
            "name": "United Kingdom",
            "version": "2026.07",
            "type": "atlas.content.map",
            "meta": {
                "country": "uk",
                "bbox": [-8.2, 49.8, 1.8, 60.9],
                "center": [-2.5, 54.5],
                "tiles_fetch": {
                    "enabled": True,
                    "mode": "protomaps_extract",
                    "size_hint_bytes": 400_000_000,
                },
            },
        }
        (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        def _fake_popen(cmd, **kwargs):
            partial = Path(cmd[3])
            partial.write_bytes(payload)
            proc = mock.Mock()
            proc.poll = mock.Mock(return_value=0)
            proc.returncode = 0
            proc.stderr = io.StringIO("")
            proc.kill = mock.Mock()
            proc.wait = mock.Mock(return_value=0)
            return proc

        with mock.patch("content_manager.ensure_pmtiles_cli", return_value=td_path / "pmtiles"), mock.patch(
            "content_manager.resolve_protomaps_planet_url",
            return_value="https://build.protomaps.com/20260721.pmtiles",
        ), mock.patch("content_manager.subprocess.Popen", side_effect=_fake_popen):
            (td_path / "pmtiles").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            (td_path / "pmtiles").chmod(0o755)
            info = fetch_map_tiles_for_manifest(manifest, target, atlas)

        assert info["ok"]
        assert info["bytes"] == len(payload)
        assert (target / "uk.pmtiles").is_file()
        index = json.loads((target / "index.json").read_text(encoding="utf-8"))
        assert index["status"] == "ready"
        registry = json.loads((atlas / "maps" / "countries.json").read_text(encoding="utf-8"))
        assert registry["countries"]["uk"]["status"] == "ready"
        assert (atlas / "nomad-storage" / "maps" / "pmtiles" / "uk.pmtiles").exists()
        prog = json.loads((atlas / "maps" / ".fetch-progress-uk").read_text(encoding="utf-8"))
        assert prog["status"] == "ready"
        assert prog["done"] is True
        assert prog["total"] == len(payload)
        assert prog["downloaded"] == len(payload)
        # Must not stay stuck at the 400MB catalogue hint after success
        assert prog["total"] != 400_000_000


def test_extract_does_not_mark_ready_on_non_pmtiles_bytes():
    import io

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        dest = td_path / "maps" / "uk"
        atlas = td_path / "atlas"
        junk = b"NOTILES" + (b"\x00" * MIN_USABLE_PMTILES_BYTES)

        def _fake_popen(cmd, **kwargs):
            Path(cmd[3]).write_bytes(junk)
            proc = mock.Mock()
            proc.poll = mock.Mock(return_value=0)
            proc.returncode = 0
            proc.stderr = io.StringIO("")
            proc.kill = mock.Mock()
            proc.wait = mock.Mock(return_value=0)
            return proc

        with mock.patch("content_manager.ensure_pmtiles_cli", return_value=td_path / "x"), mock.patch(
            "content_manager.resolve_protomaps_planet_url",
            return_value="https://build.protomaps.com/20260721.pmtiles",
        ), mock.patch("content_manager.subprocess.Popen", side_effect=_fake_popen):
            try:
                fetch_country_pmtiles(
                    dest,
                    country="uk",
                    bbox=[-8, 49, 2, 61],
                    atlas_root=atlas,
                    size_hint_bytes=400_000_000,
                )
                raise AssertionError("expected PackError for invalid magic")
            except PackError as e:
                assert "invalid" in str(e).lower() or "magic" in str(e).lower()
        prog = json.loads((atlas / "maps" / ".fetch-progress-uk").read_text(encoding="utf-8"))
        assert prog["status"] == "error"
        assert prog["done"] is True
        assert not (dest / "uk.pmtiles").exists()


def _build_uk_pack(td_path: Path, *, tile_bytes: bytes | None) -> tuple[Path, Path]:
    atlas = td_path / "atlas"
    stage = td_path / "stage"
    (stage / "payload").mkdir(parents=True)
    if tile_bytes is not None:
        (stage / "payload" / "uk.pmtiles").write_bytes(tile_bytes)
    else:
        (stage / "payload" / "README.txt").write_text("stub", encoding="utf-8")
    (stage / "licences").mkdir()
    (stage / "licences" / "ODbL.txt").write_text("ODbL", encoding="utf-8")
    manifest = {
        "schema": "atlas.pack/v1",
        "id": "atlas.maps.uk",
        "version": "2026.07",
        "type": "atlas.content.map",
        "name": "UK",
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
        "meta": {
            "country": "uk",
            "bbox": [-8, 49, 2, 61],
            "tiles_fetch": {"enabled": True, "size_hint_bytes": 400000000},
        },
        "digest": "sha256:" + ("0" * 64),
    }
    (stage / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    pack = td_path / "uk.atlas-pack"
    digest = build_pack(stage, pack)
    manifest["digest"] = digest
    (stage / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    build_pack(stage, pack)
    return pack, atlas


def test_install_with_embedded_pmtiles_marks_ready():
    with tempfile.TemporaryDirectory() as td:
        pack, atlas = _build_uk_pack(Path(td), tile_bytes=make_minimal_pmtiles())

        # Embedded usable tiles → no network fetch even if tiles_fetch enabled
        result = install_pack(pack, atlas, fetch_tiles=True)
        assert result["ok"]
        assert result["tiles_status"] == "ready"
        index = json.loads((atlas / "maps" / "uk" / "index.json").read_text(encoding="utf-8"))
        assert index["status"] == "ready"
        assert "uk.pmtiles" in index["tiles"]


def test_install_stub_or_tiny_tiles_stays_stub():
    with tempfile.TemporaryDirectory() as td:
        pack, atlas = _build_uk_pack(Path(td), tile_bytes=None)
        result = install_pack(pack, atlas, fetch_tiles=False)
        assert result["ok"]
        assert result["tiles_status"] == "stub"
        index = json.loads((atlas / "maps" / "uk" / "index.json").read_text(encoding="utf-8"))
        assert index["status"] == "stub"
        registry = json.loads((atlas / "maps" / "countries.json").read_text(encoding="utf-8"))
        assert registry["countries"]["uk"]["status"] == "stub"

    with tempfile.TemporaryDirectory() as td:
        pack, atlas = _build_uk_pack(Path(td), tile_bytes=b"tiny")
        result = install_pack(pack, atlas, fetch_tiles=False)
        assert result["tiles_status"] == "stub"
        index = json.loads((atlas / "maps" / "uk" / "index.json").read_text(encoding="utf-8"))
        assert index["status"] == "stub"


def test_merge_catalogue_exposes_tiles_status():
    from content_manager import merge_catalogue_status

    with tempfile.TemporaryDirectory() as td:
        atlas = Path(td) / "atlas"
        maps = atlas / "maps" / "uk"
        maps.mkdir(parents=True)
        (atlas / "maps" / "countries.json").write_text(
            json.dumps(
                {
                    "countries": {
                        "uk": {
                            "pack_id": "atlas.maps.uk",
                            "name": "UK",
                            "status": "stub",
                            "tiles": [],
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        (atlas / "content-packs").mkdir(parents=True)
        (atlas / "content-packs" / "installed.json").write_text(
            json.dumps(
                {
                    "packs": [
                        {
                            "id": "atlas.maps.uk",
                            "version": "2026.07",
                            "target": str(maps),
                            "type": "atlas.content.map",
                            "name": "UK",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        cat = {
            "packs": [
                {
                    "id": "atlas.maps.uk",
                    "category": "maps",
                    "country": "uk",
                    "type": "atlas.content.map",
                    "name": "UK",
                }
            ]
        }
        merged = merge_catalogue_status(cat, atlas)
        assert merged["packs"][0]["installed"] is True
        assert merged["packs"][0]["tiles_status"] == "stub"


def test_repair_maps_registry_promotes_stub_when_pmtiles_present():
    from content_manager import make_minimal_pmtiles, repair_maps_registry

    with tempfile.TemporaryDirectory() as td:
        atlas = Path(td) / "atlas"
        uk = atlas / "maps" / "uk"
        uk.mkdir(parents=True)
        (uk / "uk.pmtiles").write_bytes(make_minimal_pmtiles(80_000))
        (uk / "manifest.json").write_text(
            json.dumps(
                {
                    "id": "atlas.maps.uk",
                    "name": "United Kingdom",
                    "version": "2026.07",
                    "meta": {"country": "uk", "bbox": [-8, 49, 2, 61], "center": [-2.5, 54.5]},
                }
            ),
            encoding="utf-8",
        )
        (atlas / "maps" / "countries.json").write_text(
            json.dumps({"countries": {"uk": {"status": "stub", "tiles": [], "name": "UK"}}}),
            encoding="utf-8",
        )
        (uk / "index.json").write_text(json.dumps({"status": "stub", "tiles": []}), encoding="utf-8")

        result = repair_maps_registry(atlas)
        assert result["ok"] is True
        assert "uk" in result["repaired"]
        assert "uk" in result["ready"]
        registry = json.loads((atlas / "maps" / "countries.json").read_text(encoding="utf-8"))
        assert registry["countries"]["uk"]["status"] == "ready"
        assert "uk.pmtiles" in registry["countries"]["uk"]["tiles"]
        index = json.loads((uk / "index.json").read_text(encoding="utf-8"))
        assert index["status"] == "ready"
        assert (atlas / "nomad-storage" / "maps" / "pmtiles" / "uk.pmtiles").exists()


def test_merge_catalogue_filesystem_overrides_stub_registry():
    from content_manager import make_minimal_pmtiles, merge_catalogue_status

    with tempfile.TemporaryDirectory() as td:
        atlas = Path(td) / "atlas"
        maps = atlas / "maps" / "uk"
        maps.mkdir(parents=True)
        (maps / "uk.pmtiles").write_bytes(make_minimal_pmtiles(70_000))
        (atlas / "maps" / "countries.json").write_text(
            json.dumps({"countries": {"uk": {"status": "stub", "tiles": [], "path": str(maps)}}}),
            encoding="utf-8",
        )
        (atlas / "content-packs").mkdir(parents=True)
        (atlas / "content-packs" / "installed.json").write_text(
            json.dumps(
                {
                    "packs": [
                        {
                            "id": "atlas.maps.uk",
                            "version": "1",
                            "target": str(maps),
                            "type": "atlas.content.map",
                            "name": "UK",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        cat = {
            "packs": [
                {
                    "id": "atlas.maps.uk",
                    "category": "maps",
                    "country": "uk",
                    "type": "atlas.content.map",
                    "name": "UK",
                }
            ]
        }
        merged = merge_catalogue_status(cat, atlas)
        assert merged["packs"][0]["tiles_status"] == "ready"


def test_merge_catalogue_ignores_stale_progress_ready_without_tiles():
    from content_manager import merge_catalogue_status, write_maps_fetch_progress

    with tempfile.TemporaryDirectory() as td:
        atlas = Path(td) / "atlas"
        maps = atlas / "maps" / "uk"
        maps.mkdir(parents=True)
        (atlas / "maps" / "countries.json").write_text(
            json.dumps({"countries": {"uk": {"status": "stub", "tiles": [], "path": str(maps)}}}),
            encoding="utf-8",
        )
        write_maps_fetch_progress(
            atlas,
            {"country": "uk", "status": "ready", "done": True, "downloaded": 1, "total": 1},
            "uk",
        )
        (atlas / "content-packs").mkdir(parents=True)
        (atlas / "content-packs" / "installed.json").write_text(
            json.dumps(
                {
                    "packs": [
                        {
                            "id": "atlas.maps.uk",
                            "version": "1",
                            "target": str(maps),
                            "type": "atlas.content.map",
                            "name": "UK",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        cat = {
            "packs": [
                {
                    "id": "atlas.maps.uk",
                    "category": "maps",
                    "country": "uk",
                    "type": "atlas.content.map",
                    "name": "UK",
                }
            ]
        }
        merged = merge_catalogue_status(cat, atlas)
        assert merged["packs"][0]["tiles_status"] == "stub"


def test_read_maps_progress_does_not_cross_attribute_countries():
    from content_manager import read_maps_fetch_progress, write_maps_fetch_progress

    with tempfile.TemporaryDirectory() as td:
        atlas = Path(td) / "atlas"
        (atlas / "maps").mkdir(parents=True)
        write_maps_fetch_progress(
            atlas,
            {"country": "uk", "status": "ready", "done": True, "downloaded": 10, "total": 10},
            "uk",
        )
        # No per-country file for de — global pointer is UK and must not apply.
        (atlas / "maps" / ".fetch-progress-uk").unlink(missing_ok=True)
        de = read_maps_fetch_progress(atlas, "de")
        assert de.get("status") == "idle"
        uk = read_maps_fetch_progress(atlas, "uk")
        assert uk.get("status") == "ready"


def test_resolve_target_remaps_srv_atlas_maps():
    from content_manager import _resolve_target

    with tempfile.TemporaryDirectory() as td:
        atlas = Path(td) / "atlas-dev"
        atlas.mkdir()
        man = {
            "id": "atlas.maps.uk",
            "version": "2026.07",
            "type": "atlas.content.map",
            "mount_target": "/srv/atlas/maps/uk",
            "meta": {"country": "uk"},
        }
        target = _resolve_target(man, atlas)
        assert target == atlas / "maps" / "uk"
        # Also works when atlas_root is the classic path
        srv = Path("/srv/atlas")
        # Don't require /srv/atlas to exist — just check string remapping logic via type fallback
        man2 = {
            "id": "atlas.maps.de",
            "version": "1",
            "type": "atlas.content.map",
            "mount_target": "/var/other/maps/de",
            "meta": {"country": "de"},
        }
        assert _resolve_target(man2, atlas) == atlas / "maps" / "de"


def test_install_real_uk_pack_lands_under_maps():
    """Bundled UK stub must install to <atlas>/maps/uk, not content-packs/."""
    pack = ROOT / "packages/atlas-content-manager/usr/share/atlas/packs/atlas-maps-uk.atlas-pack"
    if not pack.is_file():
        print("SKIP test_install_real_uk_pack_lands_under_maps (pack missing)")
        return
    with tempfile.TemporaryDirectory() as td:
        atlas = Path(td) / "atlas"
        result = install_pack(pack, atlas, fetch_tiles=False)
        assert result["ok"]
        assert result["target"].endswith("/maps/uk"), result["target"]
        assert (atlas / "maps" / "uk" / "index.json").is_file()
        index = json.loads((atlas / "maps" / "uk" / "index.json").read_text(encoding="utf-8"))
        assert index["status"] == "stub"
        assert index["country"] == "uk"
        registry = json.loads((atlas / "maps" / "countries.json").read_text(encoding="utf-8"))
        assert registry["countries"]["uk"]["status"] == "stub"
        assert registry["countries"]["uk"]["path"].endswith("/maps/uk")


def test_maps_progress_indeterminate_until_bytes():
    from content_manager import _enrich_fetch_progress, write_maps_fetch_progress, read_maps_fetch_progress

    idle = _enrich_fetch_progress(
        {"country": "uk", "status": "preparing", "downloaded": 0, "total": 400_000_000, "done": False}
    )
    assert idle.get("indeterminate") is True
    assert idle.get("percent") is None
    mid = _enrich_fetch_progress(
        {"country": "uk", "status": "extracting", "downloaded": 80_000_000, "total": 400_000_000, "done": False}
    )
    assert mid["percent"] == 20.0
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write_maps_fetch_progress(
            root,
            {
                "country": "uk",
                "status": "starting",
                "done": False,
                "downloaded": 0,
                "total": 100,
                "started_at": 42.0,
            },
            "uk",
        )
        write_maps_fetch_progress(
            root,
            {"country": "uk", "status": "extracting", "done": False, "downloaded": 25, "total": 100},
            "uk",
        )
        prog = read_maps_fetch_progress(root, "uk")
        assert prog["started_at"] == 42.0
        assert prog["downloaded"] == 25
        assert prog["percent"] == 25.0


if __name__ == "__main__":
    test_should_auto_fetch_requires_tiles_fetch_meta()
    test_tiny_pmtiles_not_usable_still_wants_fetch()
    test_fetch_country_pmtiles_direct_url()
    test_fetch_country_pmtiles_rejects_tiny_download()
    test_fetch_country_pmtiles_extract_invokes_cli()
    test_fetch_map_tiles_marks_ready_only_after_reindex()
    test_extract_does_not_mark_ready_on_non_pmtiles_bytes()
    test_install_with_embedded_pmtiles_marks_ready()
    test_install_stub_or_tiny_tiles_stays_stub()
    test_merge_catalogue_exposes_tiles_status()
    test_repair_maps_registry_promotes_stub_when_pmtiles_present()
    test_merge_catalogue_filesystem_overrides_stub_registry()
    test_merge_catalogue_ignores_stale_progress_ready_without_tiles()
    test_read_maps_progress_does_not_cross_attribute_countries()
    test_resolve_target_remaps_srv_atlas_maps()
    test_install_real_uk_pack_lands_under_maps()
    test_maps_progress_indeterminate_until_bytes()
    print("OK test_maps_pmtiles_fetch")
