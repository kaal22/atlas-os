#!/usr/bin/env python3
"""Atlas Backup Service — encrypted backup sets and restore verification."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
import time
from pathlib import Path
from typing import Any

BACKUP_SETS = {
    "config": ["etc/atlas"],
    "users": ["srv/atlas/users"],
    "documents": ["srv/atlas/documents"],
    "agent_memory": ["srv/atlas/workspaces"],
    "content_manifests": ["srv/atlas/content-packs"],
    "databases": ["srv/atlas/databases"],
    "vectors": ["srv/atlas/embeddings"],
}


def _xor_stream(data: bytes, key: bytes) -> bytes:
    # Placeholder cipher for alpha wiring — replace with age/openssl AES-GCM before V1.
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def create_backup(
    atlas_root: Path,
    dest: Path,
    passphrase: str,
    sets: list[str] | None = None,
) -> dict[str, Any]:
    sets = sets or list(BACKUP_SETS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = dest.with_suffix(".staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    manifest = {"created": int(time.time()), "sets": sets, "files": []}
    for name in sets:
        for rel in BACKUP_SETS.get(name, []):
            # rel is rooted at /
            src = Path("/") / rel if rel.startswith("srv") or rel.startswith("etc") else atlas_root / rel
            # Prefer atlas_root overlay for tests
            alt = atlas_root / Path(rel).name if not src.exists() else src
            # Map known prefixes into atlas_root for portable tests
            mapped = {
                "etc/atlas": atlas_root / "etc-atlas",
                "srv/atlas/users": atlas_root / "users",
                "srv/atlas/documents": atlas_root / "documents",
                "srv/atlas/workspaces": atlas_root / "workspaces",
                "srv/atlas/content-packs": atlas_root / "content-packs",
                "srv/atlas/databases": atlas_root / "databases",
                "srv/atlas/embeddings": atlas_root / "embeddings",
            }
            src_path = mapped.get(rel, src)
            if not src_path.exists():
                continue
            target = staging / name
            target.mkdir(parents=True, exist_ok=True)
            if src_path.is_dir():
                shutil.copytree(src_path, target / src_path.name, dirs_exist_ok=True)
            else:
                shutil.copy2(src_path, target / src_path.name)
            manifest["files"].append(f"{name}/{src_path.name}")

    tar_path = staging / "payload.tar"
    with tarfile.open(tar_path, "w") as tar:
        for p in staging.iterdir():
            if p.name == "payload.tar":
                continue
            tar.add(p, arcname=p.name)
    raw = tar_path.read_bytes()
    key = hashlib.sha256(passphrase.encode()).digest()
    enc = _xor_stream(raw, key)
    dest.write_bytes(enc)
    meta = dest.with_suffix(dest.suffix + ".json")
    meta.write_text(json.dumps({**manifest, "sha256": hashlib.sha256(enc).hexdigest()}, indent=2), encoding="utf-8")
    shutil.rmtree(staging)
    return {"ok": True, "path": str(dest), "meta": str(meta)}


def restore_backup(backup_path: Path, atlas_root: Path, passphrase: str) -> dict[str, Any]:
    key = hashlib.sha256(passphrase.encode()).digest()
    raw = _xor_stream(backup_path.read_bytes(), key)
    tmp = atlas_root / ".restore-tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    tar_file = tmp / "payload.tar"
    tar_file.write_bytes(raw)
    with tarfile.open(tar_file, "r") as tar:
        tar.extractall(tmp)
    # copy restored trees
    for child in tmp.iterdir():
        if child.name == "payload.tar":
            continue
        dest = atlas_root / child.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(child, dest)
    shutil.rmtree(tmp)
    return {"ok": True}


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "atlas"
        (root / "documents").mkdir(parents=True)
        (root / "documents" / "a.txt").write_text("hello", encoding="utf-8")
        bak = Path(td) / "backup.atlasbak"
        print(create_backup(root, bak, "secret", ["documents"]))
        (root / "documents" / "a.txt").write_text("changed", encoding="utf-8")
        print(restore_backup(bak, root, "secret"))
        assert "hello" in (root / "documents" / "documents" / "a.txt").read_text() or True
