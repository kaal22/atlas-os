#!/usr/bin/env python3
"""Unit tests for atlas backup_service."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "atlas-backup" / "usr" / "lib" / "atlas"))

from backup_service import (  # noqa: E402
    BackupError,
    create_backup,
    list_backups,
    restore_backup,
    verify_backup,
)


def test_round_trip():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "atlas"
        (root / "documents").mkdir(parents=True)
        (root / "documents" / "note.txt").write_text("hello atlas", encoding="utf-8")
        (root / "databases").mkdir(parents=True)
        (root / "databases" / "auth.json").write_text('{"users":[]}', encoding="utf-8")
        bak = Path(td) / "full.atlasbak"
        result = create_backup(root, bak, "test-pass", ["documents", "databases"])
        assert result["ok"]
        assert bak.is_file()
        v = verify_backup(bak)
        assert v["ok"]
        (root / "documents" / "note.txt").write_text("changed", encoding="utf-8")
        restore_backup(bak, root, "test-pass")
        assert (root / "documents" / "note.txt").read_text(encoding="utf-8") == "hello atlas"
        assert (root / "databases" / "auth.json").is_file()


def test_bad_passphrase():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "atlas"
        (root / "documents").mkdir(parents=True)
        (root / "documents" / "a.txt").write_text("x", encoding="utf-8")
        bak = Path(td) / "b.atlasbak"
        create_backup(root, bak, "correct", ["documents"])
        try:
            restore_backup(bak, root, "wrong")
            raise AssertionError("expected BackupError")
        except BackupError as e:
            assert "passphrase" in str(e).lower() or "decrypt" in str(e).lower()


def test_verify_detects_tamper():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "atlas"
        (root / "documents").mkdir(parents=True)
        (root / "documents" / "a.txt").write_text("x", encoding="utf-8")
        bak = Path(td) / "b.atlasbak"
        create_backup(root, bak, "secret", ["documents"])
        data = bytearray(bak.read_bytes())
        data[-1] ^= 0xFF
        bak.write_bytes(bytes(data))
        try:
            verify_backup(bak)
            raise AssertionError("expected BackupError")
        except BackupError as e:
            assert "checksum" in str(e).lower() or "mismatch" in str(e).lower()


def test_list_backups():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "atlas"
        bak_dir = Path(td) / "backups"
        (root / "documents").mkdir(parents=True)
        (root / "documents" / "a.txt").write_text("x", encoding="utf-8")
        create_backup(root, bak_dir / "one.atlasbak", "p", ["documents"])
        listed = list_backups(bak_dir)
        assert len(listed) == 1
        assert listed[0]["verified"] is True


if __name__ == "__main__":
    test_round_trip()
    test_bad_passphrase()
    test_verify_detects_tamper()
    test_list_backups()
    print("OK test_backup_service")
