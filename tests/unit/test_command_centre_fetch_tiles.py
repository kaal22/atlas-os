#!/usr/bin/env python3
"""Regression tests for Command Centre map tile fetch API."""
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
from content_manager import install_pack  # noqa: E402

UK_PACK = ROOT / "packages/atlas-content-manager/usr/share/atlas/packs/atlas-maps-uk.atlas-pack"


def _setup_cc() -> tuple[str, str]:
    data = Path(tempfile.mkdtemp(prefix="atlas-cc-fetch-"))
    for sub in ("databases", "logs", "maps"):
        (data / sub).mkdir(parents=True, exist_ok=True)
    cc.DATA = data
    cc.AUTH = auth_mod.AuthStore(data / "databases" / "auth.json")
    cc.AUTH.load()
    cc.AUTH.create_owner("owner", "s3cret-pass")
    tok, csrf = cc.AUTH.login("owner", "s3cret-pass")
    install_pack(UK_PACK, data, fetch_tiles=False)
    return tok, csrf


def _post(port: int, path: str, body: dict, tok: str, csrf: str) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Cookie": f"atlas_session={tok}; atlas_csrf={csrf}",
            "X-CSRF-Token": csrf,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            obj = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            obj = {"raw": raw}
        return e.code, obj


def test_fetch_tiles_returns_json_not_empty_response():
    """fetch-tiles must not crash do_POST (threading shadowing regression)."""
    tok, csrf = _setup_cc()
    server = cc.ThreadingHTTPServer(("127.0.0.1", 0), cc.Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    port = server.server_address[1]
    try:
        code, body = _post(
            port,
            "/api/content/fetch-tiles",
            {"id": "atlas.maps.uk", "country": "uk"},
            tok,
            csrf,
        )
        assert code == 202, (code, body)
        assert body.get("tiles_status") == "fetching"
        assert body.get("country") == "uk"
        assert "target" in body
    finally:
        server.shutdown()


def test_install_path_starts_async_tile_fetch():
    """Install via pack path should return tiles_status=fetching (async thread starts)."""
    prev_skip = os.environ.pop("ATLAS_MAPS_SKIP_FETCH", None)
    try:
        data = Path(tempfile.mkdtemp(prefix="atlas-cc-install-"))
        for sub in ("databases", "logs"):
            (data / sub).mkdir(parents=True, exist_ok=True)
        cc.DATA = data
        cc.AUTH = auth_mod.AuthStore(data / "databases" / "auth.json")
        cc.AUTH.load()
        cc.AUTH.create_owner("owner", "s3cret-pass")
        tok, csrf = cc.AUTH.login("owner", "s3cret-pass")
        pack_copy = data / "atlas-maps-uk.atlas-pack"
        pack_copy.write_bytes(UK_PACK.read_bytes())

        server = cc.ThreadingHTTPServer(("127.0.0.1", 0), cc.Handler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        port = server.server_address[1]
        try:
            code, body = _post(
                port,
                "/api/content/install",
                {"path": str(pack_copy), "confirm_large": True},
                tok,
                csrf,
            )
            assert code == 200, (code, body)
            assert body.get("ok") is True
            assert body.get("tiles_status") == "fetching", body
            assert body.get("tiles_fetch") == "started"
        finally:
            server.shutdown()
    finally:
        if prev_skip is not None:
            os.environ["ATLAS_MAPS_SKIP_FETCH"] = prev_skip
        else:
            os.environ["ATLAS_MAPS_SKIP_FETCH"] = "1"


def test_maps_countries_json_repairs_stub_and_serves_pmtiles():
    """Viewer path: DATA reassignment must not desync maps_dir; stub registry repairs on GET."""
    from content_manager import make_minimal_pmtiles

    data = Path(tempfile.mkdtemp(prefix="atlas-cc-maps-"))
    for sub in ("databases", "logs", "maps/uk"):
        (data / sub).mkdir(parents=True, exist_ok=True)
    cc.DATA = data
    cc.AUTH = auth_mod.AuthStore(data / "databases" / "auth.json")
    cc.AUTH.load()
    cc.AUTH.create_owner("owner", "s3cret-pass")
    tok, csrf = cc.AUTH.login("owner", "s3cret-pass")

    uk = data / "maps" / "uk"
    (uk / "uk.pmtiles").write_bytes(make_minimal_pmtiles(90_000))
    (uk / "manifest.json").write_text(
        json.dumps({"id": "atlas.maps.uk", "name": "UK", "version": "1", "meta": {"country": "uk"}}),
        encoding="utf-8",
    )
    (data / "maps" / "countries.json").write_text(
        json.dumps({"countries": {"uk": {"status": "stub", "tiles": []}}}),
        encoding="utf-8",
    )

    server = cc.ThreadingHTTPServer(("127.0.0.1", 0), cc.Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    port = server.server_address[1]
    try:
        # maps_dir() must follow reassigned DATA (not frozen import-time MAPS_DIR).
        assert cc.maps_dir() == data / "maps"
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/maps/countries.json", timeout=5) as resp:
            reg = json.loads(resp.read().decode())
        assert reg["countries"]["uk"]["status"] == "ready", reg
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/maps/pmtiles/uk.pmtiles",
            method="HEAD",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert resp.status == 200
            assert int(resp.headers.get("Content-Length") or 0) >= 65536
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/content/maps-repair",
            timeout=5,
            # auth required for API
        ) as resp:
            # Should 401 without cookie — that's fine; countries.json path already repaired.
            pass
    except urllib.error.HTTPError as e:
        if e.code != 401:
            raise
    finally:
        server.shutdown()


if __name__ == "__main__":
    test_fetch_tiles_returns_json_not_empty_response()
    test_install_path_starts_async_tile_fetch()
    test_maps_countries_json_repairs_stub_and_serves_pmtiles()
    print("ok")
