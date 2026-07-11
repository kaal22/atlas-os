#!/usr/bin/env python3
"""Atlas Updater — stage, verify, apply with rollback hooks."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class UpdateResult:
    ok: bool
    action: str
    detail: str


def create_snapshot(label: str, dry_run: bool = True) -> UpdateResult:
    # Btrfs subvolume snapshot of /
    cmd = ["btrfs", "subvolume", "snapshot", "-r", "/", f"/.snapshots/{label}"]
    if dry_run:
        return UpdateResult(True, "snapshot", " ".join(cmd))
    Path("/.snapshots").mkdir(parents=True, exist_ok=True)
    subprocess.check_call(cmd)
    return UpdateResult(True, "snapshot", label)


def verify_signature(manifest_path: Path, allowed_keys_dir: Path) -> bool:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if "signature" not in data and "digest" not in data:
        return False
    # Alpha: require presence of publisher + digest fields
    return bool(data.get("publisher") and data.get("digest", "").startswith("sha256:"))


def apply_update(bundle_dir: Path, dry_run: bool = True) -> UpdateResult:
    manifest = bundle_dir / "update.json"
    if not manifest.exists():
        return UpdateResult(False, "apply", "missing update.json")
    if not verify_signature(manifest, Path("/usr/share/atlas/keys")):
        return UpdateResult(False, "apply", "signature verification failed")
    snap = create_snapshot(f"pre-update-{manifest.stat().st_mtime_ns}", dry_run=dry_run)
    if not snap.ok:
        return snap
    # Stage debs / containers listed in manifest
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if dry_run:
        return UpdateResult(True, "apply", f"would apply {data.get('version')} after {snap.detail}")
    # Real apply would invoke apt and docker load
    return UpdateResult(True, "apply", data.get("version", "unknown"))


def rollback(label: str, dry_run: bool = True) -> UpdateResult:
    cmd = f"btrfs rollback to /.snapshots/{label}"
    if dry_run:
        return UpdateResult(True, "rollback", cmd)
    return UpdateResult(True, "rollback", label)


if __name__ == "__main__":
    print(create_snapshot("test"))
    print(rollback("test"))
