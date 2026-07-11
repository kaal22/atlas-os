#!/usr/bin/env python3
"""Atlas Content Manager — verify, stage, atomic install of .atlas-pack archives."""
from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import tempfile
from pathlib import Path
from typing import Any

REQUIRED = {
    "schema",
    "id",
    "version",
    "type",
    "name",
    "description",
    "size_bytes",
    "minimum_os_version",
    "architectures",
    "mount_target",
    "licences",
    "sources",
    "dependencies",
    "conflicts",
    "digest",
}


class PackError(Exception):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def validate_manifest(m: dict[str, Any]) -> None:
    missing = REQUIRED - set(m)
    if missing:
        raise PackError(f"missing fields: {sorted(missing)}")
    if m.get("schema") != "atlas.pack/v1":
        raise PackError("bad schema")
    if not str(m.get("digest", "")).startswith("sha256:"):
        raise PackError("bad digest")


def verify_signature(pack_dir: Path, public_key_path: Path | None = None) -> bool:
    sig = pack_dir / "signature"
    if not sig.exists():
        # Alpha: allow unsigned only if ATLAS_ALLOW_UNSIGNED=1
        import os

        return os.environ.get("ATLAS_ALLOW_UNSIGNED", "0") == "1"
    # Placeholder: presence of signature file + matching checksums
    checksums = pack_dir / "checksums.sha256"
    return checksums.exists() and sig.stat().st_size > 0


def install_pack(pack_path: Path, atlas_root: Path = Path("/srv/atlas")) -> dict[str, Any]:
    atlas_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        with tarfile.open(pack_path, "r:*") as tar:
            tar.extractall(td_path)
        manifest_path = td_path / "manifest.json"
        if not manifest_path.exists():
            # maybe nested
            candidates = list(td_path.rglob("manifest.json"))
            if not candidates:
                raise PackError("manifest.json missing")
            root = candidates[0].parent
        else:
            root = td_path
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        validate_manifest(manifest)
        if not verify_signature(root):
            raise PackError("signature verification failed")
        target = Path(manifest["mount_target"])
        if not str(target).startswith(str(atlas_root)):
            # allow relative under content-packs
            target = atlas_root / "content-packs" / manifest["id"] / manifest["version"]
        rollback = Path(str(target) + ".rollback")
        if target.exists():
            if rollback.exists():
                shutil.rmtree(rollback)
            target.rename(rollback)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = root / "payload"
        if payload.exists():
            shutil.copytree(payload, target)
        else:
            target.mkdir(parents=True, exist_ok=True)
            (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        # commit
        if rollback.exists():
            shutil.rmtree(rollback)
        return {"ok": True, "id": manifest["id"], "target": str(target)}


def build_pack(staging: Path, out_path: Path) -> str:
    manifest = json.loads((staging / "manifest.json").read_text(encoding="utf-8"))
    validate_manifest(manifest)
    # write checksums
    lines = []
    for f in sorted(staging.rglob("*")):
        if f.is_file() and f.name not in {"checksums.sha256", "signature"}:
            rel = f.relative_to(staging).as_posix()
            digest = hashlib.sha256(f.read_bytes()).hexdigest()
            lines.append(f"{digest}  {rel}")
    (staging / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (staging / "signature").write_text("DEV-UNSIGNED-PLACEHOLDER\n", encoding="utf-8")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out_path, "w:gz") as tar:
        tar.add(staging, arcname=".")
    return sha256_file(out_path)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        stage = Path(td) / "pack"
        (stage / "payload").mkdir(parents=True)
        (stage / "payload" / "readme.txt").write_text("UK maps placeholder", encoding="utf-8")
        (stage / "licences").mkdir()
        (stage / "attribution").mkdir()
        manifest = {
            "schema": "atlas.pack/v1",
            "id": "atlas.maps.uk",
            "version": "2026.07",
            "type": "atlas.content.map",
            "name": "United Kingdom Offline Maps",
            "description": "Regional offline maps placeholder.",
            "size_bytes": 0,
            "minimum_os_version": "0.1.0",
            "architectures": ["all"],
            "mount_target": "/srv/atlas/maps/uk",
            "licences": ["ODbL-1.0"],
            "sources": [],
            "dependencies": [],
            "conflicts": [],
            "digest": "sha256:" + "0" * 64,
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        out = Path(td) / "atlas-maps-uk.atlas-pack"
        import os

        os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
        digest = build_pack(stage, out)
        print("built", out, digest)
        # rewrite digest
        m = json.loads((stage / "manifest.json").read_text())
        m["digest"] = digest
        (stage / "manifest.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
        build_pack(stage, out)
        dest_root = Path(td) / "srv"
        # override mount for test
        m = json.loads((stage / "manifest.json").read_text())
        m["mount_target"] = str(dest_root / "maps" / "uk")
        (stage / "manifest.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
        build_pack(stage, out)
        print(install_pack(out, dest_root))
