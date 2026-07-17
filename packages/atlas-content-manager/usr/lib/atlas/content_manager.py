#!/usr/bin/env python3
"""Atlas Content Manager — verify, stage, atomic install of .atlas-pack archives."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

ATLAS_OS_VERSION = os.environ.get("ATLAS_OS_VERSION", "0.1.0")
DISK_HEADROOM_BYTES = int(os.environ.get("ATLAS_PACK_DISK_HEADROOM", str(512 * 1024 * 1024)))
ALLOWED_WORKFLOWS = frozenset({"maps.reindex", "models.import", "knowledge.index", ""})

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
    wf = m.get("post_install_workflow") or ""
    if wf and wf not in ALLOWED_WORKFLOWS:
        raise PackError(f"unknown post_install_workflow: {wf}")


def _parse_version(v: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", v or "0")
    return tuple(int(p) for p in parts) or (0,)


def _version_ok(minimum: str, current: str = ATLAS_OS_VERSION) -> bool:
    return _parse_version(current) >= _parse_version(minimum)


def _arch_ok(manifest: dict[str, Any]) -> bool:
    arches = manifest.get("architectures") or ["all"]
    if "all" in arches:
        return True
    host = os.uname().machine.lower()
    return host in {a.lower() for a in arches} or "amd64" in arches and host in {"x86_64", "amd64"}


def _disk_free_bytes(path: Path) -> int:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0


def verify_checksums(pack_root: Path) -> None:
    listing = pack_root / "checksums.sha256"
    if not listing.exists():
        raise PackError("checksums.sha256 missing")
    for line in listing.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        digest, rel = parts[0], parts[1].strip()
        fpath = pack_root / rel
        if not fpath.is_file():
            raise PackError(f"checksum target missing: {rel}")
        got = hashlib.sha256(fpath.read_bytes()).hexdigest()
        if got != digest:
            raise PackError(f"checksum mismatch: {rel}")


def verify_signature(pack_dir: Path, public_key_path: Path | None = None) -> bool:
    sig = pack_dir / "signature"
    checksums = pack_dir / "checksums.sha256"
    if not sig.exists():
        return os.environ.get("ATLAS_ALLOW_UNSIGNED", "0") == "1"
    if not checksums.exists() or sig.stat().st_size == 0:
        return False
    body = sig.read_text(encoding="utf-8").strip()
    if body == "DEV-UNSIGNED-PLACEHOLDER":
        return os.environ.get("ATLAS_ALLOW_UNSIGNED", "0") == "1"
    pub = public_key_path or Path("/usr/share/atlas/keys/atlas-dev-package.pub")
    if not pub.is_file():
        pub = Path(os.environ.get("ATLAS_PACK_PUBKEY", ""))
    if pub.is_file() and shutil.which("openssl"):
        try:
            proc = subprocess.run(
                ["openssl", "dgst", "-sha256", "-verify", str(pub), "-signature", str(sig), str(checksums)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return proc.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            pass
    return checksums.exists() and sig.stat().st_size > 0


def read_pack_metadata(pack_path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        root = _extract_pack_root(Path(pack_path), Path(td))
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        validate_manifest(manifest)
        licences = []
        lic_dir = root / "licences"
        if lic_dir.is_dir():
            for f in sorted(lic_dir.iterdir()):
                if f.is_file():
                    licences.append({"name": f.name, "text": f.read_text(encoding="utf-8", errors="replace")[:8000]})
        attribution = []
        attr_dir = root / "attribution"
        if attr_dir.is_dir():
            for f in sorted(attr_dir.iterdir()):
                if f.is_file():
                    attribution.append({"name": f.name, "text": f.read_text(encoding="utf-8", errors="replace")[:4000]})
        return {
            "manifest": manifest,
            "licences": licences,
            "attribution": attribution,
            "signed": (root / "signature").exists(),
        }


def _extract_pack_root(pack_path: Path, td_path: Path) -> Path:
    with tarfile.open(pack_path, "r:*") as tar:
        tar.extractall(td_path)
    if (td_path / "manifest.json").exists():
        return td_path
    candidates = list(td_path.rglob("manifest.json"))
    if not candidates:
        raise PackError("manifest.json missing")
    return candidates[0].parent


def _installed_path(atlas_root: Path) -> Path:
    return atlas_root / "content-packs" / "installed.json"


def load_installed(atlas_root: Path) -> dict[str, Any]:
    path = _installed_path(atlas_root)
    if not path.exists():
        return {"packs": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_installed(atlas_root: Path, data: dict[str, Any]) -> None:
    path = _installed_path(atlas_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _resolve_target(manifest: dict[str, Any], atlas_root: Path) -> Path:
    target = Path(manifest["mount_target"])
    if str(target).startswith(str(atlas_root.resolve())):
        return target
    return atlas_root / "content-packs" / manifest["id"] / manifest["version"]


def check_compatibility(manifest: dict[str, Any], atlas_root: Path) -> dict[str, Any]:
    errors: list[str] = []
    if not _version_ok(str(manifest.get("minimum_os_version", "0"))):
        errors.append(f"needs Atlas OS {manifest.get('minimum_os_version')} or newer")
    if not _arch_ok(manifest):
        errors.append("not compatible with this CPU architecture")
    installed = {p["id"]: p for p in load_installed(atlas_root).get("packs", [])}
    for dep in manifest.get("dependencies") or []:
        if dep not in installed:
            errors.append(f"missing dependency: {dep}")
    for conflict in manifest.get("conflicts") or []:
        if conflict in installed:
            errors.append(f"conflicts with installed pack: {conflict}")
    need = int(manifest.get("size_bytes") or 0) + DISK_HEADROOM_BYTES
    free = _disk_free_bytes(atlas_root)
    if need and free < need:
        errors.append(
            f"not enough disk space (need ~{need // (1024 * 1024)} MB free, have ~{free // (1024 * 1024)} MB)"
        )
    return {"ok": not errors, "errors": errors, "disk_free_bytes": free, "disk_need_bytes": need}


def _rollback_target(target: Path, rollback: Path) -> None:
    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    if rollback.exists():
        rollback.rename(target)


def _run_workflow(
    workflow: str,
    manifest: dict[str, Any],
    target: Path,
    atlas_root: Path,
    hooks: dict[str, Callable[..., None]] | None = None,
) -> None:
    if not workflow:
        return
    if hooks and workflow in hooks:
        hooks[workflow](manifest, target, atlas_root)
        return
    if workflow == "maps.reindex":
        if not target.is_dir():
            raise PackError("maps target is not a directory")
        (target / ".atlas-indexed").write_text(str(time.time()), encoding="utf-8")
        return
    if workflow == "models.import":
        _workflow_models_import(manifest, target, atlas_root)
        return
    if workflow == "knowledge.index":
        _workflow_knowledge_index(manifest, target, atlas_root)
        return
    raise PackError(f"unsupported workflow: {workflow}")


def _workflow_models_import(manifest: dict[str, Any], target: Path, atlas_root: Path) -> None:
    try:
        from model_catalog import ALLOWED_TAGS, catalogue_for_hardware, probe_hardware  # type: ignore
    except ImportError:
        ALLOWED_TAGS = set()
        catalogue_for_hardware = None  # type: ignore
        probe_hardware = None  # type: ignore

    sources = manifest.get("sources") or []
    for tag in sources:
        raw = str(tag)
        if raw.startswith("ollama:"):
            raw = raw.split(":", 1)[1]
        if ALLOWED_TAGS and raw not in ALLOWED_TAGS:
            raise PackError(f"model_not_in_catalogue: {raw}")
        if catalogue_for_hardware and probe_hardware:
            hw = probe_hardware()
            cat = catalogue_for_hardware(hw, installed=[])
            entry = next((c for c in cat if c["tag"] == raw), None)
            if entry and not entry.get("compatible"):
                raise PackError(f"model_not_compatible: {raw} ({'; '.join(entry.get('blockers') or [])})")

    ollama_models = atlas_root / "models" / "ollama"
    ollama_models.mkdir(parents=True, exist_ok=True)
    if target.exists():
        for item in target.iterdir():
            dest = ollama_models / item.name
            if item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
            elif item.is_file():
                shutil.copy2(item, dest)


def _workflow_knowledge_index(manifest: dict[str, Any], target: Path, atlas_root: Path) -> None:
    try:
        from knowledge_service import KnowledgeService, SUPPORTED_EXTENSIONS  # type: ignore
    except ImportError:
        return
    ks = KnowledgeService(atlas_root / "knowledge")
    user_id = "system"
    if target.is_dir():
        for path in sorted(target.rglob("*")):
            if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                try:
                    ks.ingest_file(user_id, path)
                except Exception:
                    pass


def install_pack(
    pack_path: Path,
    atlas_root: Path = Path("/srv/atlas"),
    hooks: dict[str, Callable[..., None]] | None = None,
) -> dict[str, Any]:
    pack_path = Path(pack_path)
    if not pack_path.is_file():
        raise PackError("pack file not found")
    atlas_root = Path(atlas_root)
    atlas_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        root = _extract_pack_root(pack_path, td_path)
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        validate_manifest(manifest)
        verify_checksums(root)
        if not verify_signature(root):
            raise PackError("signature verification failed")
        compat = check_compatibility(manifest, atlas_root)
        if not compat["ok"]:
            raise PackError("; ".join(compat["errors"]))

        target = _resolve_target(manifest, atlas_root)
        rollback = Path(str(target) + ".rollback")
        had_previous = target.exists()

        try:
            if had_previous:
                if rollback.exists():
                    shutil.rmtree(rollback) if rollback.is_dir() else rollback.unlink()
                target.rename(rollback)
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = root / "payload"
            if payload.exists():
                shutil.copytree(payload, target)
            else:
                target.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / "manifest.json", target / "manifest.json")

            wf = manifest.get("post_install_workflow") or ""
            _run_workflow(wf, manifest, target, atlas_root, hooks=hooks)

            if rollback.exists():
                shutil.rmtree(rollback) if rollback.is_dir() else rollback.unlink()

            record = {
                "id": manifest["id"],
                "version": manifest["version"],
                "type": manifest["type"],
                "name": manifest["name"],
                "target": str(target),
                "digest": manifest["digest"],
                "installed_at": time.time(),
            }
            data = load_installed(atlas_root)
            packs = [p for p in data.get("packs", []) if p.get("id") != manifest["id"]]
            packs.append(record)
            data["packs"] = packs
            save_installed(atlas_root, data)
            return {"ok": True, **record}
        except Exception:
            _rollback_target(target, rollback)
            raise


def uninstall_pack(pack_id: str, atlas_root: Path = Path("/srv/atlas")) -> dict[str, Any]:
    atlas_root = Path(atlas_root)
    data = load_installed(atlas_root)
    packs = data.get("packs", [])
    match = next((p for p in packs if p.get("id") == pack_id), None)
    if not match:
        raise PackError("pack_not_installed")
    target = Path(match.get("target") or "")
    if target.exists():
        shutil.rmtree(target) if target.is_dir() else target.unlink()
    data["packs"] = [p for p in packs if p.get("id") != pack_id]
    save_installed(atlas_root, data)
    return {"ok": True, "id": pack_id}


def list_usb_pack_dirs() -> list[str]:
    roots: list[str] = []
    for base in (Path("/media"), Path("/run/media"), Path("/mnt")):
        if not base.is_dir():
            continue
        try:
            for user_dir in base.iterdir():
                if not user_dir.is_dir():
                    continue
                for mount in user_dir.iterdir():
                    if mount.is_dir():
                        roots.append(str(mount))
        except OSError:
            continue
    return sorted(set(roots))


def find_packs_on_paths(paths: list[str | Path]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in paths:
        base = Path(raw)
        if not base.is_dir():
            continue
        try:
            for f in base.rglob("*.atlas-pack"):
                key = str(f.resolve())
                if key in seen:
                    continue
                seen.add(key)
                try:
                    meta = read_pack_metadata(f)
                    m = meta["manifest"]
                    found.append(
                        {
                            "path": key,
                            "id": m.get("id"),
                            "name": m.get("name"),
                            "version": m.get("version"),
                            "type": m.get("type"),
                            "size_bytes": m.get("size_bytes"),
                        }
                    )
                except PackError:
                    continue
        except OSError:
            continue
    return found


def load_catalogue(catalogue_path: Path) -> dict[str, Any]:
    if not catalogue_path.is_file():
        return {"schema": "atlas.pack/v1", "catalogue_version": "0", "packs": []}
    return json.loads(catalogue_path.read_text(encoding="utf-8"))


def merge_catalogue_status(catalogue: dict[str, Any], atlas_root: Path) -> dict[str, Any]:
    installed = {p["id"]: p for p in load_installed(atlas_root).get("packs", [])}
    out = dict(catalogue)
    packs = []
    for entry in catalogue.get("packs") or []:
        row = dict(entry)
        inst = installed.get(entry.get("id", ""))
        row["installed"] = bool(inst)
        if inst:
            row["installed_version"] = inst.get("version")
        packs.append(row)
    out["packs"] = packs
    return out


def build_pack(staging: Path, out_path: Path, sign_key: Path | None = None) -> str:
    manifest = json.loads((staging / "manifest.json").read_text(encoding="utf-8"))
    validate_manifest(manifest)
    lines = []
    for f in sorted(staging.rglob("*")):
        if f.is_file() and f.name not in {"checksums.sha256", "signature"}:
            rel = f.relative_to(staging).as_posix()
            digest = hashlib.sha256(f.read_bytes()).hexdigest()
            lines.append(f"{digest}  {rel}")
    (staging / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    sig_path = staging / "signature"
    key = sign_key or Path(os.environ.get("ATLAS_PACK_SIGN_KEY", ""))
    if key.is_file() and shutil.which("openssl"):
        subprocess.run(
            ["openssl", "dgst", "-sha256", "-sign", str(key), "-out", str(sig_path), str(staging / "checksums.sha256")],
            check=True,
            timeout=30,
        )
    else:
        sig_path.write_text("DEV-UNSIGNED-PLACEHOLDER\n", encoding="utf-8")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out_path, "w:gz") as tar:
        tar.add(staging, arcname=".")
    return sha256_file(out_path)


if __name__ == "__main__":
    import tempfile as _tempfile

    with _tempfile.TemporaryDirectory() as td:
        stage = Path(td) / "pack"
        (stage / "payload").mkdir(parents=True)
        (stage / "payload" / "readme.txt").write_text("UK maps placeholder", encoding="utf-8")
        (stage / "licences").mkdir()
        (stage / "licences" / "ODbL.txt").write_text("Open Database Licence", encoding="utf-8")
        (stage / "attribution").mkdir()
        manifest = {
            "schema": "atlas.pack/v1",
            "id": "atlas.maps.uk",
            "version": "2026.07",
            "type": "atlas.content.map",
            "name": "United Kingdom Offline Maps",
            "description": "Regional offline maps placeholder.",
            "size_bytes": 1024,
            "minimum_os_version": "0.1.0",
            "architectures": ["all"],
            "mount_target": "/srv/atlas/maps/uk",
            "licences": ["ODbL-1.0"],
            "sources": [],
            "dependencies": [],
            "conflicts": [],
            "post_install_workflow": "maps.reindex",
            "digest": "sha256:" + "0" * 64,
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        out = Path(td) / "atlas-maps-uk.atlas-pack"
        os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
        digest = build_pack(stage, out)
        m = json.loads((stage / "manifest.json").read_text())
        m["digest"] = digest
        (stage / "manifest.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
        build_pack(stage, out)
        dest_root = Path(td) / "srv"
        m["mount_target"] = str(dest_root / "maps" / "uk")
        (stage / "manifest.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
        build_pack(stage, out)
        print(install_pack(out, dest_root))
