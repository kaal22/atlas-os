#!/usr/bin/env python3
"""sync_maps_to_nomad publishes ready country PMTiles into NOMAD storage."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages/atlas-content-manager/usr/lib/atlas"))

from content_manager import make_minimal_pmtiles, sync_maps_to_nomad  # noqa: E402


def test_sync_maps_to_nomad_links_ready_tiles():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        uk = root / "maps" / "uk"
        uk.mkdir(parents=True)
        # Fake a non-stub PMTiles (magic + size gate is 64 KiB)
        tile = uk / "uk.pmtiles"
        tile.write_bytes(make_minimal_pmtiles(70000))
        (root / "maps" / "countries.json").write_text(
            '{"countries":{"uk":{"name":"United Kingdom","status":"ready","tiles":["uk.pmtiles"],'
            '"center":[-2.5,54.5],"bbox":[-8.2,49.8,1.8,60.9]}}}\n',
            encoding="utf-8",
        )
        # Tiny stub must be ignored
        stub = root / "maps" / "ie"
        stub.mkdir()
        (stub / "ie.pmtiles").write_bytes(b"tiny")

        result = sync_maps_to_nomad(root)
        assert result["ok"] is True
        assert "uk" in result["linked"]
        assert "ie" not in result["linked"]
        link = root / "nomad-storage" / "maps" / "pmtiles" / "uk.pmtiles"
        assert link.is_symlink() or link.is_file()
        assert link.resolve() == tile.resolve() or link.stat().st_size == tile.stat().st_size
        assert (root / "nomad-storage" / "maps" / "countries.json").is_file()


if __name__ == "__main__":
    test_sync_maps_to_nomad_links_ready_tiles()
    print("OK test_sync_nomad_maps")
