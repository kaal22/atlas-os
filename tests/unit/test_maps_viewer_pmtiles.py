#!/usr/bin/env python3
"""PMTiles validation + Command Centre Range serving for maps."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for pkg in ("atlas-auth", "atlas-content-manager", "atlas-command-centre"):
    p = ROOT / "packages" / pkg / "usr" / "lib" / "atlas"
    if p.exists():
        sys.path.insert(0, str(p))

os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
os.environ["ATLAS_MAPS_SKIP_FETCH"] = "1"

import auth_store as auth_mod  # noqa: E402
import command_centre as cc  # noqa: E402
from content_manager import (  # noqa: E402
    make_minimal_pmtiles,
    validate_pmtiles_archive,
)


def test_validate_pmtiles_rejects_magic_only_stub():
    with tempfile.TemporaryDirectory(prefix="atlas-pmtiles-val-") as td:
        bad = Path(td) / "bad.pmtiles"
        bad.write_bytes(b"PMTiles" + (b"\x00" * 90_000))
        ok, reason = validate_pmtiles_archive(bad)
        assert not ok, reason
        assert "version" in reason or reason in {
            "bad_magic",
            "empty_root_directory",
            "no_tiles",
            "not_vector_tile_type:0",
        }


def test_validate_pmtiles_accepts_minimal_helper():
    with tempfile.TemporaryDirectory(prefix="atlas-pmtiles-ok-") as td:
        good = Path(td) / "uk.pmtiles"
        good.write_bytes(make_minimal_pmtiles(90_000))
        ok, reason = validate_pmtiles_archive(good)
        assert ok, reason


def test_validate_pmtiles_rejects_truncated_claim():
    """Header claims tile data past EOF → truncated (force re-fetch)."""
    raw = bytearray(make_minimal_pmtiles(90_000))
    # tile_offset @ byte 56 (8 + 6*8), tile_length @ 64
    import struct

    struct.pack_into("<Q", raw, 56, 130)  # tile offset
    struct.pack_into("<Q", raw, 64, 50_000_000)  # claim 50MB of tile data
    with tempfile.TemporaryDirectory(prefix="atlas-pmtiles-trunc-") as td:
        path = Path(td) / "uk.pmtiles"
        path.write_bytes(bytes(raw))
        ok, reason = validate_pmtiles_archive(path)
        assert not ok
        assert reason == "truncated_tile_data"


def test_command_centre_pmtiles_range_206():
    data = Path(tempfile.mkdtemp(prefix="atlas-cc-range-"))
    for sub in ("databases", "logs", "maps/uk"):
        (data / sub).mkdir(parents=True, exist_ok=True)
    cc.DATA = data
    # Force UI reload isn't needed; maps handler uses filesystem viewer.
    cc.AUTH = auth_mod.AuthStore(data / "databases" / "auth.json")
    cc.AUTH.load()
    cc.AUTH.create_owner("owner", "s3cret-pass")

    tile = data / "maps" / "uk" / "uk.pmtiles"
    tile.write_bytes(make_minimal_pmtiles(90_000))
    (data / "maps" / "countries.json").write_text(
        json.dumps({"countries": {"uk": {"name": "United Kingdom", "status": "ready", "tiles": ["uk.pmtiles"]}}}),
        encoding="utf-8",
    )

    server = cc.ThreadingHTTPServer(("127.0.0.1", 0), cc.Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    port = server.server_address[1]
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/maps/pmtiles/uk.pmtiles",
            headers={"Range": "bytes=0-126"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 206, resp.status
            assert resp.headers.get("Accept-Ranges") == "bytes"
            cr = resp.headers.get("Content-Range") or ""
            assert cr.startswith("bytes 0-126/"), cr
            body = resp.read()
            assert len(body) == 127
            assert body[:7] == b"PMTiles"
            assert body[7] == 3

        # /maps (no slash) must redirect so asset URLs resolve under /maps/
        class _NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: N802
                return None

        opener = urllib.request.build_opener(_NoRedirect)
        try:
            opener.open(f"http://127.0.0.1:{port}/maps?country=uk", timeout=5)
            assert False, "expected 301 redirect"
        except urllib.error.HTTPError as e:
            assert e.code == 301, e.code
            assert e.headers.get("Location") == "/maps/?country=uk", e.headers.get("Location")

        app_js = (
            ROOT
            / "packages"
            / "atlas-maps-viewer"
            / "usr"
            / "share"
            / "atlas"
            / "maps-viewer"
            / "lib"
            / "atlas-maps-app.js"
        )
        assert app_js.is_file(), app_js
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/maps/lib/atlas-maps-app.js", timeout=5) as resp:
            assert resp.status == 200
            body = resp.read()
            assert b"AtlasMaps" in body
    finally:
        server.shutdown()


def test_resolve_rejects_corrupt_pmtiles():
    data = Path(tempfile.mkdtemp(prefix="atlas-cc-corrupt-"))
    (data / "maps" / "uk").mkdir(parents=True)
    cc.DATA = data
    bad = data / "maps" / "uk" / "uk.pmtiles"
    bad.write_bytes(b"PMTiles" + (b"\x00" * 90_000))
    assert cc.resolve_country_pmtiles("uk") is None
    bad.write_bytes(make_minimal_pmtiles(90_000))
    assert cc.resolve_country_pmtiles("uk") == bad


def test_maps_viewer_paint_first_contract():
    """Paint-first style + diagnostics must exist so blank maps cannot fail silently."""
    app_js = (
        ROOT
        / "packages"
        / "atlas-maps-viewer"
        / "usr"
        / "share"
        / "atlas"
        / "maps-viewer"
        / "lib"
        / "atlas-maps-app.js"
    )
    index = (
        ROOT
        / "packages"
        / "atlas-maps-viewer"
        / "usr"
        / "share"
        / "atlas"
        / "maps-viewer"
        / "index.html"
    )
    text = app_js.read_text(encoding="utf-8")
    html = index.read_text(encoding="utf-8")
    assert "paint-first" in text
    assert "buildPaintFirstStyle" in text
    assert "queryRenderedFeatures" in text
    assert "atlasMapsDiag" in text or "collectDiagnostics" in text
    assert 'id="map"' in text or "mapEl.id = \"map\"" in text
    assert "pmtiles://" in text and "/{z}/{x}/{y}" in text
    assert "earth" in text and "water" in text and "roads" in text
    assert cc.PROTOMAPS_V4_LAYERS[0] == "earth"
    assert "water" in cc.PROTOMAPS_V4_LAYERS
    # Stable source id (not country code) — avoids MapLibre isSourceLoaded('uk') spam
    # and basemaps lang "uk" = Ukrainian collision.
    assert 'TILE_SOURCE = "protomaps"' in text or "TILE_SOURCE = 'protomaps'" in text
    assert "safeSourceLoaded" in text
    assert "There is no source with ID" in text  # filtered in error handler
    assert "atlas-diag-bbox" in text
    # Empty-state CTA must not cover a painted map (inline display used to defeat [hidden]).
    assert "setPanelVisible" in text
    assert "hideEmptyOverlay" in text
    assert "MAP OK" in text
    assert "defeated [hidden]" in text or "overrides UA [hidden]" in text
    # Empty chrome must not set display:grid in cssText (only via setPanelVisible when shown).
    assert "empty.style.cssText" in text
    empty_css = text.split("empty.style.cssText")[1].split("setPanelVisible(empty")[0]
    assert "display:grid" not in empty_css
    assert "display:flex" not in empty_css or "bar.style" in empty_css
    assert "assertStyleSources" in text
    assert "diff: false" in text or "diff:!1" in text or 'diff: false' in text
    # Full-viewport paint surface so blank vs tiles is obvious.
    assert "height: 100%" in html
    assert "#0b6e99" in html or "0b6e99" in html

    # Logic mirror of buildPaintFirstStyle: every v4 layer gets an unfiltered fill
    # against the stable TILE_SOURCE id, plus diag geojson source.
    tile_source = "protomaps"
    layers = [{"id": "background", "type": "background"}]
    for name in cc.PROTOMAPS_V4_LAYERS:
        layers.append(
            {
                "id": f"atlas-fill-{name}",
                "type": "fill",
                "source": tile_source,
                "source-layer": name,
            }
        )
    fills = [layer for layer in layers if layer["type"] == "fill"]
    assert len(fills) == len(cc.PROTOMAPS_V4_LAYERS)
    assert all("filter" not in layer for layer in fills)
    assert all(layer["source"] == tile_source for layer in fills)


def test_maps_diag_endpoint():
    data = Path(tempfile.mkdtemp(prefix="atlas-cc-diag-"))
    for sub in ("databases", "logs", "maps/uk"):
        (data / sub).mkdir(parents=True, exist_ok=True)
    cc.DATA = data
    cc.AUTH = auth_mod.AuthStore(data / "databases" / "auth.json")
    cc.AUTH.load()
    cc.AUTH.create_owner("owner", "s3cret-pass")

    tile = data / "maps" / "uk" / "uk.pmtiles"
    tile.write_bytes(make_minimal_pmtiles(90_000))
    (data / "maps" / "countries.json").write_text(
        json.dumps(
            {
                "countries": {
                    "uk": {
                        "name": "United Kingdom",
                        "status": "ready",
                        "tiles": ["uk.pmtiles"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    server = cc.ThreadingHTTPServer(("127.0.0.1", 0), cc.Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    port = server.server_address[1]
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/maps/diag", timeout=5) as resp:
            assert resp.status == 200
            body = json.loads(resp.read().decode())
        assert body.get("ok") is True
        assert "expected_protomaps_v4_layers" in body
        assert "earth" in body["expected_protomaps_v4_layers"]
        assert body.get("countries", {}).get("uk", {}).get("tiles_ok") is True
        assert body.get("atlas_maps_app", {}).get("has_paint_first") is True
    finally:
        server.shutdown()


if __name__ == "__main__":
    test_validate_pmtiles_rejects_magic_only_stub()
    test_validate_pmtiles_accepts_minimal_helper()
    test_validate_pmtiles_rejects_truncated_claim()
    test_command_centre_pmtiles_range_206()
    test_resolve_rejects_corrupt_pmtiles()
    test_maps_viewer_paint_first_contract()
    test_maps_diag_endpoint()
    print("ok")
