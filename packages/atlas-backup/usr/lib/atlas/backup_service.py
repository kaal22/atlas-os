#!/usr/bin/env python3
"""Atlas Backup Service — encrypted backup sets and restore verification."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any

FORMAT_VERSION = 1
MAGIC = b"ATLASBAK1"
BACKUP_SETS = {
    "config": "etc/atlas",
    "users": "users",
    "documents": "documents",
    "agent_memory": "workspaces",
    "content_manifests": "content-packs",
    "databases": "databases",
    "knowledge": "knowledge",
    "vectors": "embeddings",
}


class BackupError(Exception):
    pass


def _resolve_set_path(atlas_root: Path, set_name: str) -> Path:
    rel = BACKUP_SETS[set_name]
    if set_name == "config":
        live = Path("/etc/atlas")
        if atlas_root.resolve() == Path("/srv/atlas").resolve() and live.exists():
            return live
        return atlas_root / "etc" / "atlas"
    return atlas_root / rel


def _openssl_encrypt(plaintext: bytes, passphrase: str) -> bytes:
    """AES-256-CBC with PBKDF2 via openssl (already on Atlas images)."""
    with tempfile.NamedTemporaryFile(delete=False) as inn, tempfile.NamedTemporaryFile(delete=False) as out:
        in_path, out_path = Path(inn.name), Path(out.name)
        inn.write(plaintext)
        inn.flush()
    try:
        proc = subprocess.run(
            [
                "openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt",
                "-pass", f"pass:{passphrase}",
                "-in", str(in_path), "-out", str(out_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            raise BackupError(f"encrypt failed: {proc.stderr.strip() or proc.stdout.strip()}")
        return out_path.read_bytes()
    finally:
        in_path.unlink(missing_ok=True)
        out_path.unlink(missing_ok=True)


def _openssl_decrypt(ciphertext: bytes, passphrase: str) -> bytes:
    with tempfile.NamedTemporaryFile(delete=False) as inn, tempfile.NamedTemporaryFile(delete=False) as out:
        in_path, out_path = Path(inn.name), Path(out.name)
        inn.write(ciphertext)
        inn.flush()
    try:
        proc = subprocess.run(
            [
                "openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2",
                "-pass", f"pass:{passphrase}",
                "-in", str(in_path), "-out", str(out_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if proc.returncode != 0:
            raise BackupError("decrypt failed — wrong passphrase or corrupt backup")
        return out_path.read_bytes()
    finally:
        in_path.unlink(missing_ok=True)
        out_path.unlink(missing_ok=True)


def _meta_path(backup_path: Path) -> Path:
    return backup_path.with_suffix(backup_path.suffix + ".json")


def create_backup(
    atlas_root: Path,
    dest: Path,
    passphrase: str,
    sets: list[str] | None = None,
) -> dict[str, Any]:
    if not passphrase:
        raise BackupError("passphrase_required")
    atlas_root = Path(atlas_root)
    dest = Path(dest)
    sets = sets or list(BACKUP_SETS)
    unknown = [s for s in sets if s not in BACKUP_SETS]
    if unknown:
        raise BackupError(f"unknown sets: {unknown}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        staging = Path(td) / "stage"
        staging.mkdir()
        for name in sets:
            src_path = _resolve_set_path(atlas_root, name)
            if not src_path.exists():
                continue
            target = staging / name
            target.mkdir(parents=True, exist_ok=True)
            if src_path.is_dir():
                for child in src_path.iterdir():
                    dest_child = target / child.name
                    if child.is_dir():
                        shutil.copytree(child, dest_child, dirs_exist_ok=True)
                    else:
                        shutil.copy2(child, dest_child)
                    files.append(f"{name}/{child.name}")
            else:
                shutil.copy2(src_path, target / src_path.name)
                files.append(f"{name}/{src_path.name}")

        tar_path = Path(td) / "payload.tar"
        with tarfile.open(tar_path, "w") as tar:
            for p in staging.iterdir():
                tar.add(p, arcname=p.name)
        raw = tar_path.read_bytes()
        enc = _openssl_encrypt(raw, passphrase)
        blob = MAGIC + enc
        dest.write_bytes(blob)

    manifest = {
        "format_version": FORMAT_VERSION,
        "created": int(time.time()),
        "sets": sets,
        "files": files,
        "sha256": hashlib.sha256(blob).hexdigest(),
        "cipher": "openssl-aes-256-cbc-pbkdf2",
    }
    meta = _meta_path(dest)
    meta.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"ok": True, "path": str(dest), "meta": str(meta), "sets": sets, "files": files}


def verify_backup(backup_path: Path) -> dict[str, Any]:
    backup_path = Path(backup_path)
    meta_path = _meta_path(backup_path)
    if not backup_path.is_file():
        raise BackupError("backup_not_found")
    if not meta_path.is_file():
        raise BackupError("meta_missing")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    data = backup_path.read_bytes()
    if not data.startswith(MAGIC):
        raise BackupError("bad_magic")
    digest = hashlib.sha256(data).hexdigest()
    if digest != meta.get("sha256"):
        raise BackupError("checksum_mismatch")
    return {"ok": True, "meta": meta, "size_bytes": len(data)}


def list_backups(backup_dir: Path) -> list[dict[str, Any]]:
    backup_dir = Path(backup_dir)
    if not backup_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for f in sorted(backup_dir.glob("*.atlasbak"), key=lambda p: p.stat().st_mtime, reverse=True):
        row: dict[str, Any] = {"path": str(f), "name": f.name, "size_bytes": f.stat().st_size}
        meta_path = _meta_path(f)
        if meta_path.is_file():
            try:
                row["meta"] = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                row["meta"] = None
        try:
            verify_backup(f)
            row["verified"] = True
        except BackupError as e:
            row["verified"] = False
            row["verify_error"] = str(e)
        out.append(row)
    return out


def restore_backup(backup_path: Path, atlas_root: Path, passphrase: str) -> dict[str, Any]:
    if not passphrase:
        raise BackupError("passphrase_required")
    backup_path = Path(backup_path)
    atlas_root = Path(atlas_root)
    verify_backup(backup_path)

    data = backup_path.read_bytes()
    enc = data[len(MAGIC):]
    raw = _openssl_decrypt(enc, passphrase)

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        tar_file = td_path / "payload.tar"
        tar_file.write_bytes(raw)
        extract = td_path / "extract"
        extract.mkdir()
        try:
            with tarfile.open(tar_file, "r") as tar:
                tar.extractall(extract, filter="data")
        except tarfile.TarError as e:
            raise BackupError(f"corrupt_payload: {e}") from e

        restored: list[str] = []
        for child in extract.iterdir():
            if not child.is_dir():
                continue
            set_name = child.name
            if set_name not in BACKUP_SETS:
                continue
            dest = _resolve_set_path(atlas_root, set_name)
            staging = Path(str(dest) + ".restore-staging")
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True)
            for item in child.iterdir():
                target = staging / item.name
                if item.is_dir():
                    shutil.copytree(item, target, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, target)
            dest.parent.mkdir(parents=True, exist_ok=True)
            rollback = Path(str(dest) + ".rollback")
            if dest.exists():
                if rollback.exists():
                    shutil.rmtree(rollback) if rollback.is_dir() else rollback.unlink()
                dest.rename(rollback)
            staging.rename(dest)
            if rollback.exists():
                shutil.rmtree(rollback) if rollback.is_dir() else rollback.unlink()
            restored.append(set_name)

    return {"ok": True, "restored": restored, "path": str(backup_path)}


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "atlas"
        (root / "documents").mkdir(parents=True)
        (root / "documents" / "a.txt").write_text("hello", encoding="utf-8")
        bak = Path(td) / "backup.atlasbak"
        print(create_backup(root, bak, "secret", ["documents"]))
        print(verify_backup(bak))
        (root / "documents" / "a.txt").write_text("changed", encoding="utf-8")
        print(restore_backup(bak, root, "secret"))
        assert (root / "documents" / "a.txt").read_text() == "hello"
        print("OK")
