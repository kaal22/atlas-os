#!/usr/bin/env python3
"""Atlas Content Manager — verify, stage, atomic install of .atlas-pack archives."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ATLAS_OS_VERSION = os.environ.get("ATLAS_OS_VERSION", "0.1.0")
DISK_HEADROOM_BYTES = int(os.environ.get("ATLAS_PACK_DISK_HEADROOM", str(512 * 1024 * 1024)))
ALLOWED_WORKFLOWS = frozenset({"maps.reindex", "models.import", "knowledge.index", ""})
# Protomaps daily basemap (ODbL / © OpenStreetMap). Hotlinking full planet is discouraged;
# we only pull a bbox extract via HTTP range requests (pmtiles CLI).
PMTILES_CLI_VERSION = os.environ.get("ATLAS_PMTILES_CLI_VERSION", "1.31.1")
DEFAULT_PMTILES_MAXZOOM = int(os.environ.get("ATLAS_PMTILES_MAXZOOM", "11"))
# Below this size a .pmtiles is treated as a stub/placeholder (matches /maps serving + NOMAD sync).
MIN_USABLE_PMTILES_BYTES = 65536
USER_AGENT = "AtlasOS-ContentManager/0.1 (+offline-maps; https://atlas.local)"
LARGE_MAP_WARN_BYTES = 1_000_000_000
# Default install-time Wikipedia ZIM: English top-100 articles, no pictures (~13 MiB).
# Full mini/nopic/maxi dumps are separate catalogue SKUs (size_class=large, confirm_large).
# Override any pack with ATLAS_ZIM_URL / ATLAS_ZIM_NAME.
DEFAULT_WIKIPEDIA_ZIM_URL = (
    "https://download.kiwix.org/zim/wikipedia/wikipedia_en_100_nopic_2026-04.zim"
)
DEFAULT_WIKIPEDIA_ZIM_NAME = "wikipedia_en_100_nopic.zim"
DEFAULT_WIKIPEDIA_ZIM_SIZE_HINT = 14_000_000
LARGE_ZIM_WARN_BYTES = 1_000_000_000

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


class FetchCancelledError(PackError):
    """User cancelled an in-flight map tile or ZIM download."""


_FETCH_CANCEL_LOCK = threading.Lock()
_FETCH_CANCEL: dict[str, dict[str, Any]] = {}


def _fetch_cancel_key(kind: str, ident: str) -> str:
    return f"{kind}:{ident.strip().lower()}"


def register_fetch_cancel(
    kind: str,
    ident: str,
    *,
    partials: list[Path | str] | None = None,
) -> tuple[threading.Event, str]:
    key = _fetch_cancel_key(kind, ident)
    event = threading.Event()
    entry: dict[str, Any] = {
        "event": event,
        "proc": None,
        "partials": [str(p) for p in (partials or [])],
    }
    with _FETCH_CANCEL_LOCK:
        _FETCH_CANCEL[key] = entry
    return event, key


def unregister_fetch_cancel(key: str) -> None:
    with _FETCH_CANCEL_LOCK:
        _FETCH_CANCEL.pop(key, None)


def _set_fetch_proc(key: str, proc: subprocess.Popen[str]) -> None:
    with _FETCH_CANCEL_LOCK:
        entry = _FETCH_CANCEL.get(key)
        if entry is not None:
            entry["proc"] = proc


def _cleanup_fetch_partials(partials: list[str]) -> None:
    for raw in partials:
        try:
            Path(raw).unlink(missing_ok=True)
        except OSError:
            pass


def _signal_fetch_cancel(kind: str, ident: str) -> bool:
    """Set cancel flag, kill subprocess, and remove partial files. Returns True if a job was registered."""
    key = _fetch_cancel_key(kind, ident)
    with _FETCH_CANCEL_LOCK:
        entry = _FETCH_CANCEL.get(key)
    if not entry:
        return False
    entry["event"].set()
    proc = entry.get("proc")
    if proc is not None and proc.poll() is None:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    _cleanup_fetch_partials(list(entry.get("partials") or []))
    return True


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
    """Map pack mount_target onto the active atlas data root.

    Packs ship with absolute paths like ``/srv/atlas/maps/uk``. When Command Centre
    uses a different root (e.g. ``/tmp/atlas-dev``), remap the ``/srv/atlas`` prefix
    so maps land under ``<atlas_root>/maps/<cc>`` — never under content-packs.
    """
    atlas_root = Path(atlas_root)
    try:
        atlas_resolved = atlas_root.resolve()
    except OSError:
        atlas_resolved = atlas_root
    raw = Path(manifest["mount_target"])
    if not raw.is_absolute():
        return atlas_root / raw

    try:
        raw_resolved = raw.resolve()
    except OSError:
        raw_resolved = raw

    if str(raw_resolved).startswith(str(atlas_resolved)):
        return raw_resolved

    # Remap classic /srv/atlas/... mounts onto the active data root.
    srv = Path("/srv/atlas")
    raw_s = str(raw)
    if raw_s == str(srv) or raw_s.startswith(str(srv) + "/"):
        try:
            return atlas_root / raw.relative_to(srv)
        except ValueError:
            pass

    # Well-known content layouts by pack type (prefer over opaque content-packs/).
    mtype = str(manifest.get("type") or "")
    meta = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
    if mtype == "atlas.content.map" or mtype.endswith(".map"):
        cc = str(meta.get("country") or raw.name or "").strip().lower()
        if re.fullmatch(r"[a-z]{2}", cc):
            return atlas_root / "maps" / cc
    if "knowledge" in mtype or "education" in mtype:
        # Keep relative tail when path looks like /srv/atlas/knowledge/...
        parts = raw.parts
        if "knowledge" in parts:
            idx = parts.index("knowledge")
            return atlas_root.joinpath(*parts[idx:])
        if "kolibri" in parts:
            idx = parts.index("kolibri")
            return atlas_root.joinpath(*parts[idx:])

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
        _workflow_maps_reindex(manifest, target, atlas_root)
        return
    if workflow == "models.import":
        _workflow_models_import(manifest, target, atlas_root)
        return
    if workflow == "knowledge.index":
        _workflow_knowledge_index(manifest, target, atlas_root)
        return
    raise PackError(f"unsupported workflow: {workflow}")


def _country_code_from_manifest(manifest: dict[str, Any], target: Path) -> str:
    meta = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
    code = str(meta.get("country") or "").strip().lower()
    if code:
        return code
    # Fallback: last path segment of mount target (/srv/atlas/maps/uk → uk)
    name = target.name.strip().lower()
    if re.fullmatch(r"[a-z]{2}", name):
        return name
    return "xx"


def _pmtiles_magic_ok(path: Path) -> bool:
    """PMTiles v3 archives begin with the ASCII magic ``PMTiles``."""
    try:
        with path.open("rb") as fh:
            return fh.read(7) == b"PMTiles"
    except OSError:
        return False


def read_pmtiles_header(path: Path) -> dict[str, Any] | None:
    """Parse a PMTiles v3 fixed header (127 bytes). Returns None if unreadable/invalid magic."""
    try:
        with path.open("rb") as fh:
            buf = fh.read(127)
    except OSError:
        return None
    if len(buf) < 127 or buf[:7] != b"PMTiles":
        return None
    version = buf[7]
    (
        root_offset,
        root_length,
        metadata_offset,
        metadata_length,
        leaf_offset,
        leaf_length,
        tile_offset,
        tile_length,
        addressed_tiles,
        tile_entries,
        tile_contents,
    ) = struct.unpack_from("<11Q", buf, 8)
    clustered, internal_compression, tile_compression, tile_type = buf[96:100]
    min_zoom, max_zoom = buf[100], buf[101]
    min_lon_e7, min_lat_e7, max_lon_e7, max_lat_e7 = struct.unpack_from("<4i", buf, 102)
    center_zoom = buf[118]
    center_lon_e7, center_lat_e7 = struct.unpack_from("<2i", buf, 119)
    return {
        "version": version,
        "root_offset": root_offset,
        "root_length": root_length,
        "metadata_offset": metadata_offset,
        "metadata_length": metadata_length,
        "leaf_offset": leaf_offset,
        "leaf_length": leaf_length,
        "tile_offset": tile_offset,
        "tile_length": tile_length,
        "addressed_tiles": addressed_tiles,
        "tile_entries": tile_entries,
        "tile_contents": tile_contents,
        "clustered": clustered,
        "internal_compression": internal_compression,
        "tile_compression": tile_compression,
        "tile_type": tile_type,
        "min_zoom": min_zoom,
        "max_zoom": max_zoom,
        "min_lon": min_lon_e7 / 10_000_000.0,
        "min_lat": min_lat_e7 / 10_000_000.0,
        "max_lon": max_lon_e7 / 10_000_000.0,
        "max_lat": max_lat_e7 / 10_000_000.0,
        "center_zoom": center_zoom,
        "center_lon": center_lon_e7 / 10_000_000.0,
        "center_lat": center_lat_e7 / 10_000_000.0,
    }


def validate_pmtiles_archive(path: Path) -> tuple[bool, str]:
    """Return (ok, reason). Rejects stubs, truncated extracts, and non-vector archives."""
    try:
        size = path.stat().st_size
    except OSError:
        return False, "missing"
    if size < MIN_USABLE_PMTILES_BYTES:
        return False, "too_small"
    header = read_pmtiles_header(path)
    if not header:
        return False, "bad_magic"
    if header["version"] != 3:
        return False, f"unsupported_version:{header['version']}"
    if header["tile_type"] not in (1, 6):  # MVT / MapLibre vector
        return False, f"not_vector_tile_type:{header['tile_type']}"
    if header["min_zoom"] > header["max_zoom"]:
        return False, "bad_zoom_range"
    if header["root_length"] == 0:
        return False, "empty_root_directory"
    # Truncation: claimed sections must fit in the file.
    for name, offset, length in (
        ("root", header["root_offset"], header["root_length"]),
        ("metadata", header["metadata_offset"], header["metadata_length"]),
        ("leaf", header["leaf_offset"], header["leaf_length"]),
        ("tile_data", header["tile_offset"], header["tile_length"]),
    ):
        if length and offset + length > size:
            return False, f"truncated_{name}"
    has_tiles = (
        header["tile_length"] > 0
        or header["tile_entries"] > 0
        or header["addressed_tiles"] > 0
        or header["tile_contents"] > 0
    )
    if not has_tiles:
        return False, "no_tiles"
    if header["min_lon"] >= header["max_lon"] or header["min_lat"] >= header["max_lat"]:
        return False, "bad_bounds"
    return True, "ok"


def _tile_file_usable(path: Path) -> bool:
    """True when a tile archive is large enough to serve offline (not a stub placeholder)."""
    try:
        if not path.is_file():
            return False
        suffix = path.suffix.lower()
        if suffix not in {".pmtiles", ".mbtiles", ".pbf"}:
            return False
        if suffix == ".pmtiles":
            ok, _reason = validate_pmtiles_archive(path)
            return ok
        return path.stat().st_size > 0
    except OSError:
        return False


def make_minimal_pmtiles(size: int = MIN_USABLE_PMTILES_BYTES) -> bytes:
    """Test/helper bytes that pass ``validate_pmtiles_archive`` (valid v3 header + padding)."""
    n = max(int(size), MIN_USABLE_PMTILES_BYTES)
    root_off, root_len = 127, 1
    meta_off, meta_len = 128, 2
    leaf_off, leaf_len = 0, 0
    tile_off, tile_len = 130, 1
    parts: list[bytes] = [b"PMTiles", bytes([3])]
    for v in (
        root_off,
        root_len,
        meta_off,
        meta_len,
        leaf_off,
        leaf_len,
        tile_off,
        tile_len,
        1,
        1,
        1,
    ):
        parts.append(struct.pack("<Q", v))
    # clustered, internal=none, tile=none, type=MVT
    parts.append(bytes([1, 1, 1, 1]))
    parts.append(bytes([0, 5]))  # min/max zoom
    for deg in (-8.2, 49.8, 1.8, 60.9):
        parts.append(struct.pack("<i", int(deg * 10_000_000)))
    parts.append(bytes([5]))  # center zoom
    for deg in (-2.5, 54.5):
        parts.append(struct.pack("<i", int(deg * 10_000_000)))
    hdr = b"".join(parts)
    if len(hdr) != 127:
        raise RuntimeError(f"pmtiles header size {len(hdr)} != 127")
    buf = bytearray(n)
    buf[:127] = hdr
    buf[127] = 0
    buf[128:130] = b"{}"
    buf[130] = 0
    return bytes(buf)


def _list_tile_files(target: Path, *, usable_only: bool = False) -> list[str]:
    if not target.is_dir():
        return []
    names: list[str] = []
    for p in target.iterdir():
        if not p.is_file() or p.suffix.lower() not in {".pmtiles", ".mbtiles", ".pbf"}:
            continue
        if usable_only and not _tile_file_usable(p):
            continue
        names.append(p.name)
    return sorted(names)


def has_usable_map_tiles(target: Path) -> bool:
    """True when target holds real offline tiles (not stub-only / tiny placeholders)."""
    return bool(_list_tile_files(target, usable_only=True))


def resolve_country_meta(code: str, countries_doc: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Look up country bbox/center/size hints from countries.json-shaped data."""
    code = (code or "").strip().lower()
    if not code:
        return None
    countries = (countries_doc or {}).get("countries") or []
    for row in countries:
        if str(row.get("code", "")).lower() == code:
            return dict(row)
    return None


def maps_fetch_progress_path(atlas_root: Path, country: str | None = None) -> Path:
    root = Path(atlas_root) / "maps"
    root.mkdir(parents=True, exist_ok=True)
    if country:
        return root / f".fetch-progress-{country.lower()}"
    return root / ".fetch-progress"


def _enrich_fetch_progress(payload: dict[str, Any]) -> dict[str, Any]:
    """Ensure progress payloads expose percent / bytes fields for Content UI polls."""
    data = dict(payload)
    downloaded = int(data.get("downloaded") or 0)
    total = int(data.get("total") or 0)
    data["downloaded"] = downloaded
    data["total"] = total
    done = bool(data.get("done"))
    data["done"] = done
    if total > 0 and downloaded > 0:
        raw_pct = 100.0 * min(downloaded, total) / total
        # Keep UI under 100% until the fetch reports done (hint totals are approximate).
        if done:
            data["percent"] = round(min(100.0, raw_pct), 1)
        else:
            data["percent"] = round(min(99.0, raw_pct), 1)
    elif total > 0 and downloaded == 0 and not done:
        # Distinct from "unknown" so the UI can show an indeterminate busy bar.
        data["percent"] = None
        data["indeterminate"] = True
    else:
        data.setdefault("percent", None)
        if not done and downloaded <= 0:
            data["indeterminate"] = True
    data.setdefault("status", "idle" if not data.get("status") else data.get("status"))
    data["updated_at"] = float(data.get("updated_at") or time.time())
    if data.get("started_at") is None and not done:
        data["started_at"] = data["updated_at"]
    return data


def write_maps_fetch_progress(atlas_root: Path, payload: dict[str, Any], country: str | None = None) -> None:
    cc = country or (payload.get("country") if isinstance(payload, dict) else None)
    # Preserve started_at across updates so the UI can show elapsed time.
    if cc and "started_at" not in payload:
        try:
            prev = read_maps_fetch_progress(atlas_root, str(cc))
            if prev.get("started_at") and not prev.get("done"):
                payload = {**payload, "started_at": prev["started_at"]}
        except Exception:  # noqa: BLE001
            pass
    data = _enrich_fetch_progress(payload)
    path = maps_fetch_progress_path(atlas_root, cc)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    # Also write the latest global pointer for simple UI polls.
    if cc:
        maps_fetch_progress_path(atlas_root).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def read_maps_fetch_progress(atlas_root: Path, country: str | None = None) -> dict[str, Any]:
    idle = {"downloaded": 0, "total": 0, "done": False, "status": "idle", "percent": None}
    cc = (country or "").strip().lower() or None
    path = maps_fetch_progress_path(atlas_root, cc)
    # Only fall back to the global pointer when it matches this country — otherwise
    # a finished UK fetch can make DE/FR look "ready" in the catalogue.
    if not path.is_file() and cc:
        global_path = maps_fetch_progress_path(atlas_root)
        if global_path.is_file():
            try:
                gdata = json.loads(global_path.read_text(encoding="utf-8"))
                if isinstance(gdata, dict) and str(gdata.get("country") or "").strip().lower() == cc:
                    path = global_path
            except (json.JSONDecodeError, OSError):
                pass
    elif not path.is_file() and not cc:
        path = maps_fetch_progress_path(atlas_root)
    if not path.is_file():
        return dict(idle)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            if cc and str(data.get("country") or "").strip().lower() not in {"", cc}:
                return dict(idle)
            return _enrich_fetch_progress(data)
        return dict(idle)
    except (json.JSONDecodeError, OSError):
        return {"downloaded": 0, "total": 0, "done": False, "status": "error", "percent": None}


def request_cancel_maps_fetch(
    atlas_root: Path,
    country: str,
    *,
    pack_id: str | None = None,
) -> dict[str, Any]:
    cc = country.strip().lower()
    if not cc:
        return {"ok": False, "error": "country_required"}
    prog = read_maps_fetch_progress(atlas_root, cc)
    active_statuses = {
        "starting",
        "preparing",
        "downloading",
        "extracting",
        "finalizing",
        "waiting",
        "warning",
        "running",
    }
    active = _signal_fetch_cancel("maps", cc)
    if not active and prog.get("status") not in active_statuses:
        return {"ok": False, "error": "not_running", "status": prog.get("status") or "idle"}
    payload: dict[str, Any] = {
        "country": cc,
        "status": "cancelled",
        "done": True,
        "message": "Download cancelled",
    }
    if pack_id:
        payload["pack_id"] = pack_id
    if prog.get("downloaded"):
        payload["downloaded"] = prog["downloaded"]
    if prog.get("total"):
        payload["total"] = prog["total"]
    write_maps_fetch_progress(atlas_root, payload, cc)
    return {"ok": True, "status": "cancelled", "country": cc}


def _http_head_ok(url: str, timeout: float = 15.0) -> bool:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= getattr(resp, "status", 200) < 400
    except (urllib.error.URLError, TimeoutError, OSError):
        # Some mirrors reject HEAD; try a 1-byte range GET.
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"},
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return 200 <= getattr(resp, "status", 200) < 400
        except (urllib.error.URLError, TimeoutError, OSError):
            return False


def resolve_protomaps_planet_url() -> str:
    """Pick a Protomaps daily planet URL (override with ATLAS_PMTILES_PLANET_URL)."""
    override = (os.environ.get("ATLAS_PMTILES_PLANET_URL") or "").strip()
    if override:
        return override
    today = datetime.date.today()
    for delta in range(0, 21):
        day = today - datetime.timedelta(days=delta)
        url = f"https://build.protomaps.com/{day.strftime('%Y%m%d')}.pmtiles"
        if _http_head_ok(url):
            return url
    raise PackError(
        "no recent Protomaps planet build found; set ATLAS_PMTILES_PLANET_URL "
        "or ATLAS_PMTILES_URL (direct country file)"
    )


def _pmtiles_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "x86_64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    raise PackError(f"unsupported architecture for pmtiles CLI: {machine}")


def ensure_pmtiles_cli(
    atlas_root: Path,
    *,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
) -> Path:
    """Return path to pmtiles binary, downloading the official release if needed."""
    which = shutil.which("pmtiles")
    if which:
        return Path(which)
    cache = Path(atlas_root) / "cache" / "bin"
    cache.mkdir(parents=True, exist_ok=True)
    binary = cache / "pmtiles"
    if binary.is_file() and os.access(binary, os.X_OK):
        return binary
    arch = _pmtiles_arch()
    ver = PMTILES_CLI_VERSION
    url = (
        f"https://github.com/protomaps/go-pmtiles/releases/download/v{ver}/"
        f"go-pmtiles_{ver}_Linux_{arch}.tar.gz"
    )
    if progress_cb:
        progress_cb(
            {
                "status": "preparing",
                "phase": "cli_download",
                "done": False,
                "downloaded": 0,
                "total": 0,
                "message": "Downloading pmtiles CLI (one-time setup)…",
            }
        )
    with tempfile.TemporaryDirectory() as td:
        tgz = Path(td) / "pmtiles.tgz"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp, tgz.open("wb") as out:
                total = int(resp.headers.get("Content-Length") or 0)
                downloaded = 0
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(
                            {
                                "status": "preparing",
                                "phase": "cli_download",
                                "done": False,
                                "downloaded": downloaded,
                                "total": total,
                                "message": "Downloading pmtiles CLI (one-time setup)…",
                            }
                        )
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise PackError(f"failed to download pmtiles CLI: {e}") from e
        with tarfile.open(tgz, "r:gz") as tar:
            tar.extractall(path=td)
        extracted = Path(td) / "pmtiles"
        if not extracted.is_file():
            raise PackError("pmtiles binary missing from release archive")
        shutil.copy2(extracted, binary)
        binary.chmod(0o755)
    if progress_cb:
        progress_cb(
            {
                "status": "preparing",
                "phase": "cli_ready",
                "done": False,
                "downloaded": 0,
                "total": 0,
                "message": "pmtiles CLI ready — starting tile extract…",
            }
        )
    return binary


def _download_url_to_file(
    url: str,
    dest: Path,
    *,
    progress_cb: Callable[[int, int], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".partial")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=300) as resp, partial.open("wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            downloaded = 0
            while True:
                if cancel_event and cancel_event.is_set():
                    if partial.exists():
                        partial.unlink(missing_ok=True)
                    raise FetchCancelledError("download cancelled")
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                downloaded += len(chunk)
                if progress_cb:
                    progress_cb(downloaded, total)
    except FetchCancelledError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        if partial.exists():
            partial.unlink(missing_ok=True)
        raise PackError(f"tile download failed: {e}") from e
    partial.replace(dest)


def fetch_country_pmtiles(
    target: Path,
    *,
    country: str,
    bbox: list[float] | tuple[float, ...],
    maxzoom: int | None = None,
    direct_url: str | None = None,
    atlas_root: Path = Path("/srv/atlas"),
    progress_file: Path | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    size_hint_bytes: int = 0,
) -> Path:
    """
    Fetch country tiles into target/<cc>.pmtiles.

    Prefer ATLAS_PMTILES_URL / direct_url for a finished archive; otherwise extract a
    bbox from the Protomaps daily planet with the pmtiles CLI (range requests).
    """
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    country = country.strip().lower()
    out = target / f"{country}.pmtiles"
    zoom = int(maxzoom if maxzoom is not None else DEFAULT_PMTILES_MAXZOOM)
    url = (direct_url or os.environ.get("ATLAS_PMTILES_URL") or "").strip() or None
    hint = int(size_hint_bytes or 0)
    partial_dl = out.with_suffix(out.suffix + ".partial")
    partial_extract = out.with_suffix(".pmtiles.partial")
    cancel_event, cancel_key = register_fetch_cancel(
        "maps",
        country,
        partials=[partial_dl, partial_extract],
    )

    def _emit(payload: dict[str, Any]) -> None:
        data = {
            "country": country,
            "path": str(out),
            "maxzoom": zoom,
            "licence": "ODbL-1.0",
            "attribution": "© OpenStreetMap contributors (Protomaps basemap)",
            "updated_at": time.time(),
            **payload,
        }
        if progress_file is not None:
            progress_file.parent.mkdir(parents=True, exist_ok=True)
            progress_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        write_maps_fetch_progress(atlas_root, data, country)
        if progress_cb:
            progress_cb(data)

    def _cancelled() -> None:
        if partial_dl.exists():
            partial_dl.unlink(missing_ok=True)
        if partial_extract.exists():
            partial_extract.unlink(missing_ok=True)
        _emit(
            {
                "status": "cancelled",
                "done": True,
                "message": "Download cancelled",
                "total": hint,
            }
        )

    try:
        return _fetch_country_pmtiles_body(
            target=target,
            country=country,
            out=out,
            zoom=zoom,
            url=url,
            hint=hint,
            bbox=bbox,
            atlas_root=atlas_root,
            progress_file=progress_file,
            progress_cb=progress_cb,
            cancel_event=cancel_event,
            cancel_key=cancel_key,
            _emit=_emit,
            _cancelled=_cancelled,
        )
    finally:
        unregister_fetch_cancel(cancel_key)


def _fetch_country_pmtiles_body(
    *,
    target: Path,
    country: str,
    out: Path,
    zoom: int,
    url: str | None,
    hint: int,
    bbox: list[float] | tuple[float, ...],
    atlas_root: Path,
    progress_file: Path | None,
    progress_cb: Callable[[dict[str, Any]], None] | None,
    cancel_event: threading.Event,
    cancel_key: str,
    _emit: Callable[[dict[str, Any]], None],
    _cancelled: Callable[[], None],
) -> Path:
    if cancel_event.is_set():
        _cancelled()
        raise FetchCancelledError("download cancelled")

    _emit(
        {
            "status": "starting",
            "phase": "starting",
            "downloaded": 0,
            "total": hint,
            "done": False,
            "started_at": time.time(),
            "message": "Starting map tile download…",
            "indeterminate": True,
        }
    )

    if url:
        _emit(
            {
                "status": "downloading",
                "phase": "direct_download",
                "source": url,
                "downloaded": 0,
                "total": hint,
                "done": False,
                "message": "Downloading map tiles…",
                "indeterminate": hint <= 0,
            }
        )

        def _cb(downloaded: int, total: int) -> None:
            _emit(
                {
                    "status": "downloading",
                    "phase": "direct_download",
                    "source": url,
                    "downloaded": downloaded,
                    "total": total or hint,
                    "done": False,
                    "message": "Downloading map tiles…",
                }
            )

        try:
            _download_url_to_file(url, out, progress_cb=_cb, cancel_event=cancel_event)
        except FetchCancelledError:
            _cancelled()
            raise
        if cancel_event.is_set():
            _cancelled()
            raise FetchCancelledError("download cancelled")
        ok, reason = validate_pmtiles_archive(out)
        if not ok:
            try:
                out.unlink(missing_ok=True)
            except OSError:
                pass
            _emit({"status": "error", "done": True, "error": f"downloaded_tiles_invalid:{reason}", "total": hint})
            raise PackError(
                f"downloaded PMTiles invalid ({reason}) — delete and re-fetch from Content"
            )
        final_size = out.stat().st_size
        # Do not mark done/ready here — caller must reindex then emit ready.
        _emit(
            {
                "status": "finalizing",
                "phase": "finalizing",
                "source": url,
                "downloaded": final_size,
                "total": final_size,
                "done": False,
                "bytes": final_size,
                "eta_seconds": None,
                "message": (
                    f"Download finished ({format_bytes(final_size)}); indexing for Maps…"
                    + (
                        f" (catalogue estimate was {format_bytes(hint)})"
                        if hint > 0 and abs(hint - final_size) > max(hint * 0.15, 5_000_000)
                        else ""
                    )
                ),
            }
        )
        return out

    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        raise PackError("bbox [min_lon,min_lat,max_lon,max_lat] required for Protomaps extract")
    bbox_s = ",".join(str(float(x)) for x in bbox)

    def _prep(payload: dict[str, Any]) -> None:
        # CLI download bytes must not masquerade as tile bytes in the Content bar.
        cli_dl = int(payload.get("downloaded") or 0)
        cli_tot = int(payload.get("total") or 0)
        msg = str(payload.get("message") or "Preparing…")
        if cli_tot > 0:
            msg = f"{msg} ({cli_dl // 1024} / {cli_tot // 1024} KB)"
        elif cli_dl > 0:
            msg = f"{msg} ({cli_dl // 1024} KB)"
        _emit(
            {
                **{k: v for k, v in payload.items() if k not in {"downloaded", "total"}},
                "downloaded": 0,
                "total": hint,
                "cli_downloaded": cli_dl,
                "cli_total": cli_tot,
                "message": msg,
                "indeterminate": True,
                "done": False,
            }
        )

    _emit(
        {
            "status": "preparing",
            "phase": "planet_lookup",
            "downloaded": 0,
            "total": hint,
            "done": False,
            "message": "Looking up Protomaps daily planet build…",
            "indeterminate": True,
        }
    )
    planet = resolve_protomaps_planet_url()
    if cancel_event.is_set():
        _cancelled()
        raise FetchCancelledError("download cancelled")
    _emit(
        {
            "status": "preparing",
            "phase": "cli_check",
            "source": planet,
            "downloaded": 0,
            "total": hint,
            "done": False,
            "message": "Checking pmtiles CLI…",
            "indeterminate": True,
        }
    )
    cli = ensure_pmtiles_cli(atlas_root, progress_cb=_prep)
    _emit(
        {
            "status": "extracting",
            "phase": "extract",
            "source": planet,
            "bbox": list(bbox),
            "downloaded": 0,
            "total": hint,
            "done": False,
            "message": f"Extracting z0–{zoom} from Protomaps (range requests)…",
            "indeterminate": True,
        }
    )
    partial = out.with_suffix(".pmtiles.partial")
    if partial.exists():
        partial.unlink()
    cmd = [
        str(cli),
        "extract",
        planet,
        str(partial),
        f"--bbox={bbox_s}",
        f"--maxzoom={zoom}",
    ]

    stop_monitor = threading.Event()
    last_sz = 0
    last_growth_t = time.time()
    ema_rate = 0.0
    # pmtiles extract often pauses between HTTP range batches; warn before treating as hung.
    stall_warn_s = int(os.environ.get("ATLAS_PMTILES_STALL_SECONDS", "45"))
    stderr_chunks: list[str] = []

    def _monitor_partial() -> None:
        nonlocal last_sz, last_growth_t, ema_rate
        while not stop_monitor.wait(1.0):
            try:
                sz = partial.stat().st_size if partial.is_file() else 0
                now = time.time()
                if sz > last_sz:
                    dt = max(now - last_growth_t, 0.001)
                    instant = (sz - last_sz) / dt
                    ema_rate = instant if ema_rate <= 0 else (0.35 * instant + 0.65 * ema_rate)
                    last_sz = sz
                    last_growth_t = now
                stall_seconds = int(max(0.0, now - last_growth_t))
                stalled = stall_seconds >= stall_warn_s and sz > 0
                rate = 0.0 if stalled else ema_rate
                if stalled:
                    ema_rate = 0.0
                # Never invent an ETA from a single burst while still far from the size hint.
                eta = None
                if rate >= 8_192 and hint > sz and not stalled:
                    eta = int((hint - sz) / rate)
                    if eta < 15 and sz < hint * 0.85:
                        eta = None
                msg = f"Extracting z0–{zoom} from Protomaps…"
                if stalled:
                    msg = (
                        f"Still extracting… no file growth for {stall_seconds}s "
                        f"(HTTP range pauses are normal; cancel/retry if this persists)"
                    )
                elif stall_seconds >= 8 and sz > 0:
                    msg += f" (no growth for {stall_seconds}s — still working)"
                elif rate > 0:
                    msg += f" (~{format_rate(rate)})"
                payload: dict[str, Any] = {
                    "status": "extracting",
                    "phase": "extract",
                    "source": planet,
                    "bbox": list(bbox),
                    "downloaded": sz,
                    "total": hint if hint > 0 else (sz if sz > 0 else 0),
                    "done": False,
                    "message": msg,
                    "bytes_per_sec": int(rate),
                    "stall_seconds": stall_seconds,
                    "stalled": stalled,
                    "indeterminate": sz <= 0,
                }
                if eta is not None:
                    payload["eta_seconds"] = eta
                else:
                    payload["eta_seconds"] = None
                _emit(payload)
            except OSError:
                pass

    def _drain_stderr(stream: Any) -> None:
        try:
            if stream is None:
                return
            for line in stream:
                stderr_chunks.append(line)
                if sum(len(x) for x in stderr_chunks) > 32_000:
                    del stderr_chunks[:-50]
        except (OSError, ValueError):
            pass

    monitor = threading.Thread(target=_monitor_partial, daemon=True)
    monitor.start()
    proc: subprocess.Popen[str] | None = None
    drain: threading.Thread | None = None
    extract_timeout = int(os.environ.get("ATLAS_PMTILES_EXTRACT_TIMEOUT", "7200"))
    deadline = time.time() + extract_timeout
    try:
        # IMPORTANT: never leave stdout/stderr unread — pmtiles logs fill the pipe
        # buffer (~64KiB) and deadlock mid-extract with a frozen partial size.
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        _set_fetch_proc(cancel_key, proc)
        drain = threading.Thread(target=_drain_stderr, args=(proc.stderr,), daemon=True)
        drain.start()
        while proc.poll() is None:
            if cancel_event.is_set():
                proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                if partial.exists():
                    partial.unlink(missing_ok=True)
                _cancelled()
                raise FetchCancelledError("download cancelled")
            if time.time() > deadline:
                proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                if partial.exists():
                    partial.unlink(missing_ok=True)
                _emit({"status": "error", "done": True, "error": "extract_timeout", "total": hint})
                raise PackError("pmtiles extract timed out")
            time.sleep(0.5)
    finally:
        stop_monitor.set()
        monitor.join(timeout=2.0)
        if drain is not None:
            drain.join(timeout=2.0)

    if cancel_event.is_set():
        _cancelled()
        raise FetchCancelledError("download cancelled")

    if proc is None or proc.returncode != 0 or not partial.is_file():
        err = "".join(stderr_chunks).strip()
        if not err:
            err = f"extract failed (exit {getattr(proc, 'returncode', None)})"
        if partial.exists():
            partial.unlink(missing_ok=True)
        _emit({"status": "error", "done": True, "error": err[:500], "total": hint})
        raise PackError(f"pmtiles extract failed: {err[:300]}")
    # Only promote partial → final after a successful exit; size_hint is never completion criteria.
    partial.replace(out)
    ok, reason = validate_pmtiles_archive(out)
    if not ok:
        try:
            out.unlink(missing_ok=True)
        except OSError:
            pass
        _emit({"status": "error", "done": True, "error": f"extracted_tiles_invalid:{reason}", "total": hint})
        raise PackError(
            f"extracted PMTiles invalid ({reason}) — delete and re-fetch from Content"
        )
    final_size = out.stat().st_size
    # Ready/done is emitted only after reindex (see fetch_map_tiles_for_manifest).
    _emit(
        {
            "status": "finalizing",
            "phase": "finalizing",
            "source": planet,
            "bbox": list(bbox),
            "downloaded": final_size,
            "total": final_size,
            "done": False,
            "bytes": final_size,
            "stalled": False,
            "stall_seconds": 0,
            "eta_seconds": None,
            "bytes_per_sec": 0,
            "message": (
                f"Extract finished ({format_bytes(final_size)}); indexing for Maps…"
                + (
                    f" (catalogue estimate was {format_bytes(hint)})"
                    if hint > 0 and abs(hint - final_size) > max(hint * 0.15, 5_000_000)
                    else ""
                )
            ),
        }
    )
    return out


def format_bytes(n: int | float) -> str:
    n = float(n or 0)
    if n >= 1e9:
        return f"{n / 1e9:.1f} GB"
    if n >= 1e6:
        return f"{n / 1e6:.1f} MB"
    if n >= 1e3:
        return f"{n / 1e3:.0f} KB"
    return f"{int(n)} B"


def format_rate(bytes_per_sec: float) -> str:
    if bytes_per_sec >= 1e6:
        return f"{bytes_per_sec / 1e6:.1f} MB/s"
    if bytes_per_sec >= 1e3:
        return f"{bytes_per_sec / 1e3:.0f} KB/s"
    return f"{int(bytes_per_sec)} B/s"


def _tiles_fetch_config(manifest: dict[str, Any]) -> dict[str, Any]:
    meta = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
    cfg = meta.get("tiles_fetch") if isinstance(meta.get("tiles_fetch"), dict) else {}
    return dict(cfg)


def maps_skip_fetch_env() -> bool:
    return os.environ.get("ATLAS_MAPS_SKIP_FETCH", "").strip().lower() in {"1", "true", "yes"}


def should_auto_fetch_map_tiles(manifest: dict[str, Any], target: Path) -> bool:
    if maps_skip_fetch_env():
        return False
    if (manifest.get("type") or "") != "atlas.content.map":
        return False
    # Only skip when real usable tiles are already present (tiny placeholders still fetch).
    if has_usable_map_tiles(target):
        return False
    cfg = _tiles_fetch_config(manifest)
    # Require explicit tiles_fetch in pack meta (country stubs declare this).
    if not cfg:
        return False
    if cfg.get("enabled") is False:
        return False
    if cfg.get("url") or os.environ.get("ATLAS_PMTILES_URL"):
        return True
    meta = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
    bbox = cfg.get("bbox") or meta.get("bbox")
    return isinstance(bbox, (list, tuple)) and len(bbox) == 4


def fetch_map_tiles_for_manifest(
    manifest: dict[str, Any],
    target: Path,
    atlas_root: Path,
    *,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Download tiles for an installed map pack target, then caller should reindex."""
    meta = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
    cfg = _tiles_fetch_config(manifest)
    country = _country_code_from_manifest(manifest, target)
    bbox = cfg.get("bbox") or meta.get("bbox")
    maxzoom = cfg.get("maxzoom")
    if maxzoom is None:
        maxzoom = DEFAULT_PMTILES_MAXZOOM
    direct = (cfg.get("url") or os.environ.get("ATLAS_PMTILES_URL") or "").strip() or None
    hint = int(cfg.get("size_hint_bytes") or meta.get("size_hint_bytes") or 0)
    if hint >= LARGE_MAP_WARN_BYTES:
        write_maps_fetch_progress(
            atlas_root,
            {
                "country": country,
                "status": "warning",
                "done": False,
                "downloaded": 0,
                "total": hint,
                "message": f"Large download (~{hint // (1024**3)}+ GiB estimated). Continuing…",
                "licence": "ODbL-1.0",
            },
            country,
        )
    path = fetch_country_pmtiles(
        target,
        country=country,
        bbox=list(bbox) if bbox else [],
        maxzoom=int(maxzoom),
        direct_url=direct,
        atlas_root=atlas_root,
        progress_cb=progress_cb,
        size_hint_bytes=hint,
    )
    # Reindex + NOMAD sync before declaring ready so /maps picker sees the country.
    try:
        _workflow_maps_reindex(manifest, target, atlas_root)
        repair_maps_registry(atlas_root)
    except Exception as e:  # noqa: BLE001
        write_maps_fetch_progress(
            atlas_root,
            {
                "country": country,
                "status": "error",
                "done": True,
                "error": f"reindex_failed: {e}",
                "downloaded": path.stat().st_size if path.is_file() else 0,
                "total": path.stat().st_size if path.is_file() else hint,
                "message": "Tiles downloaded but Maps index failed — retry from Content",
            },
            country,
        )
        raise PackError(f"maps reindex failed after tile fetch: {e}") from e
    if not has_usable_map_tiles(target):
        write_maps_fetch_progress(
            atlas_root,
            {
                "country": country,
                "status": "error",
                "done": True,
                "error": "tiles_not_usable_after_fetch",
                "message": "Fetch finished but tiles are not usable offline",
            },
            country,
        )
        raise PackError("tiles not usable after fetch/reindex")
    final_size = path.stat().st_size
    write_maps_fetch_progress(
        atlas_root,
        {
            "country": country,
            "status": "ready",
            "phase": "ready",
            "done": True,
            "downloaded": final_size,
            "total": final_size,
            "bytes": final_size,
            "path": str(path),
            "eta_seconds": None,
            "stalled": False,
            "message": (
                f"Tiles ready offline ({format_bytes(final_size)})"
                + (
                    f" — smaller than catalogue estimate {format_bytes(hint)}, which is normal"
                    if hint > 0 and final_size < hint * 0.85
                    else ""
                )
            ),
            "licence": "ODbL-1.0",
            "attribution": "© OpenStreetMap contributors (Protomaps basemap)",
        },
        country,
    )
    if progress_cb:
        progress_cb(
            {
                "country": country,
                "status": "ready",
                "done": True,
                "downloaded": final_size,
                "total": final_size,
                "path": str(path),
            }
        )
    return {
        "ok": True,
        "country": country,
        "path": str(path),
        "bytes": final_size,
        "maxzoom": int(maxzoom),
        "licence": "ODbL-1.0",
        "attribution": "© OpenStreetMap contributors (Protomaps basemap)",
    }


def _workflow_maps_reindex(manifest: dict[str, Any], target: Path, atlas_root: Path) -> None:
    if not target.is_dir():
        raise PackError("maps target is not a directory")
    meta = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
    country = _country_code_from_manifest(manifest, target)
    # All tile-looking files (for diagnostics); ready only when usable offline.
    tiles_all = _list_tile_files(target, usable_only=False)
    tiles = _list_tile_files(target, usable_only=True)
    index = {
        "id": manifest.get("id"),
        "country": country,
        "name": manifest.get("name"),
        "version": manifest.get("version"),
        "tiles": tiles,
        "tiles_all": tiles_all,
        "bbox": meta.get("bbox"),
        "center": meta.get("center"),
        "indexed_at": time.time(),
        "status": "ready" if tiles else "stub",
        "format": meta.get("format") or "pmtiles",
        "licence": "ODbL-1.0",
        "attribution": "© OpenStreetMap contributors",
    }
    if meta.get("tiles_fetch"):
        index["tiles_fetch"] = meta.get("tiles_fetch")
    (target / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    (target / ".atlas-indexed").write_text(str(time.time()), encoding="utf-8")
    # Aggregate country registry under /srv/atlas/maps/countries.json
    maps_root = atlas_root / "maps"
    maps_root.mkdir(parents=True, exist_ok=True)
    registry_path = maps_root / "countries.json"
    registry: dict[str, Any] = {"countries": {}}
    if registry_path.is_file():
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            if not isinstance(registry.get("countries"), dict):
                registry["countries"] = {}
        except (json.JSONDecodeError, OSError):
            registry = {"countries": {}}
    registry["countries"][country] = {
        "pack_id": manifest.get("id"),
        "name": manifest.get("name"),
        "version": manifest.get("version"),
        "path": str(target),
        "status": index["status"],
        "tiles": tiles,
        "bbox": meta.get("bbox"),
        "center": meta.get("center"),
    }
    registry["updated_at"] = time.time()
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    # Publish ready tiles into NOMAD MapLibre storage (pmtiles/ + countries.json)
    sync_maps_to_nomad(atlas_root)


def sync_maps_to_nomad(atlas_root: Path = Path("/srv/atlas")) -> dict[str, Any]:
    """Symlink /srv/atlas/maps/<cc>/<cc>.pmtiles into NOMAD's maps/pmtiles/ and seed assets.

    Prefers /usr/lib/atlas/sync-nomad-maps.sh when present; otherwise does a minimal
    Python link so tiles appear at http://127.0.0.1:8090/pmtiles/<cc>.pmtiles.
    """
    atlas_root = Path(atlas_root)
    maps_root = atlas_root / "maps"
    nomad_maps = atlas_root / "nomad-storage" / "maps"
    pmtiles_dir = nomad_maps / "pmtiles"
    pmtiles_dir.mkdir(parents=True, exist_ok=True)

    script = Path("/usr/lib/atlas/sync-nomad-maps.sh")
    if script.is_file() and os.access(script, os.X_OK):
        try:
            subprocess.run(
                [str(script)],
                check=False,
                env={
                    **os.environ,
                    "ATLAS_ROOT": str(atlas_root),
                    "ATLAS_MAPS_ROOT": str(maps_root),
                    "NOMAD_STORAGE_PATH": str(atlas_root / "nomad-storage"),
                },
                timeout=120,
                capture_output=True,
                text=True,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    linked: list[str] = []
    if maps_root.is_dir():
        for country_dir in sorted(maps_root.iterdir()):
            if not country_dir.is_dir():
                continue
            cc = country_dir.name.lower()
            if len(cc) != 2 or not cc.isalpha():
                continue
            tile = country_dir / f"{cc}.pmtiles"
            if not tile.is_file():
                candidates = list(country_dir.glob("*.pmtiles"))
                if len(candidates) != 1:
                    continue
                tile = candidates[0]
            if not _tile_file_usable(tile):
                continue
            dest = pmtiles_dir / f"{cc}.pmtiles"
            try:
                if dest.is_symlink() or dest.exists():
                    dest.unlink()
                dest.symlink_to(tile.resolve())
                linked.append(cc)
            except OSError:
                try:
                    shutil.copy2(tile, dest)
                    linked.append(cc)
                except OSError:
                    pass

    registry_src = maps_root / "countries.json"
    if registry_src.is_file():
        try:
            shutil.copy2(registry_src, nomad_maps / "countries.json")
        except OSError:
            pass

    return {"ok": True, "linked": linked, "pmtiles_dir": str(pmtiles_dir)}


# Public alias for Command Centre / external callers
reindex_maps = _workflow_maps_reindex


def repair_maps_registry(atlas_root: Path = Path("/srv/atlas")) -> dict[str, Any]:
    """Scan maps/<cc>/ for usable PMTiles and repair countries.json / index.json.

    After a successful tile download the Content UI may already show ready (from
    fetch progress), while countries.json still says stub — or an older catalogue-
    shaped countries.json may be present. The Maps viewer only lists countries that
    are ready *and* whose /maps/pmtiles/<cc>.pmtiles HEAD succeeds; a stale
    registry leaves the viewer empty. Call this before serving countries.json.
    """
    atlas_root = Path(atlas_root)
    maps_root = atlas_root / "maps"
    maps_root.mkdir(parents=True, exist_ok=True)
    registry_path = maps_root / "countries.json"
    registry: dict[str, Any] = {"countries": {}}
    if registry_path.is_file():
        try:
            raw = json.loads(registry_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict) and isinstance(raw.get("countries"), dict):
                registry = raw
            # Array / catalogue-shaped docs are not the runtime registry — rebuild.
        except (json.JSONDecodeError, OSError):
            registry = {"countries": {}}
    if not isinstance(registry.get("countries"), dict):
        registry["countries"] = {}

    repaired: list[str] = []
    ready: list[str] = []
    for country_dir in sorted(maps_root.iterdir()):
        if not country_dir.is_dir():
            continue
        cc = country_dir.name.strip().lower()
        if not re.fullmatch(r"[a-z]{2}", cc):
            continue
        tiles = _list_tile_files(country_dir, usable_only=True)
        if not tiles:
            # Keep existing stub entries; do not invent countries without tiles.
            continue
        ready.append(cc)
        manifest: dict[str, Any] = {}
        mp = country_dir / "manifest.json"
        if mp.is_file():
            try:
                loaded = json.loads(mp.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    manifest = loaded
            except (json.JSONDecodeError, OSError):
                pass
        meta = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
        index: dict[str, Any] = {}
        index_path = country_dir / "index.json"
        if index_path.is_file():
            try:
                loaded = json.loads(index_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    index = loaded
            except (json.JSONDecodeError, OSError):
                pass
        prev = registry["countries"].get(cc) if isinstance(registry["countries"].get(cc), dict) else {}
        entry = {
            "pack_id": manifest.get("id") or prev.get("pack_id") or index.get("id"),
            "name": manifest.get("name") or prev.get("name") or index.get("name") or cc.upper(),
            "version": manifest.get("version") or prev.get("version") or index.get("version"),
            "path": str(country_dir),
            "status": "ready",
            "tiles": tiles,
            "bbox": meta.get("bbox") or prev.get("bbox") or index.get("bbox"),
            "center": meta.get("center") or prev.get("center") or index.get("center"),
        }
        if (
            prev.get("status") != "ready"
            or prev.get("tiles") != tiles
            or str(prev.get("path") or "") != str(country_dir)
            or index.get("status") != "ready"
        ):
            repaired.append(cc)
        registry["countries"][cc] = entry
        index.update(
            {
                "id": entry.get("pack_id") or index.get("id"),
                "country": cc,
                "name": entry.get("name"),
                "version": entry.get("version"),
                "tiles": tiles,
                "bbox": entry.get("bbox"),
                "center": entry.get("center"),
                "indexed_at": time.time(),
                "status": "ready",
                "format": index.get("format") or meta.get("format") or "pmtiles",
                "licence": index.get("licence") or "ODbL-1.0",
                "attribution": index.get("attribution") or "© OpenStreetMap contributors",
            }
        )
        try:
            index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
            (country_dir / ".atlas-indexed").write_text(str(time.time()), encoding="utf-8")
        except OSError:
            pass

    registry["updated_at"] = time.time()
    try:
        registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    except OSError as e:
        return {"ok": False, "error": str(e), "repaired": repaired, "ready": ready}

    linked: list[str] = []
    if repaired or ready:
        try:
            sync_result = sync_maps_to_nomad(atlas_root)
            linked = list(sync_result.get("linked") or [])
        except Exception:  # noqa: BLE001
            linked = []
    return {"ok": True, "repaired": repaired, "ready": ready, "linked": linked}


def _pack_slug(manifest: dict[str, Any], target: Path | None = None) -> str:
    raw = str(manifest.get("id") or (target.name if target else "pack"))
    slug = raw.rsplit(".", 1)[-1].strip().lower()
    slug = re.sub(r"[^a-z0-9_-]+", "-", slug).strip("-")
    return slug or "pack"


def zim_fetch_progress_path(atlas_root: Path, pack_slug: str | None = None) -> Path:
    root = Path(atlas_root) / "knowledge"
    root.mkdir(parents=True, exist_ok=True)
    if pack_slug:
        return root / f".zim-fetch-progress-{pack_slug}"
    return root / ".zim-fetch-progress"


def write_zim_fetch_progress(atlas_root: Path, payload: dict[str, Any], pack_slug: str | None = None) -> None:
    data = _enrich_fetch_progress(payload)
    slug = pack_slug or data.get("pack_slug")
    if slug:
        data["pack_slug"] = slug
    path = zim_fetch_progress_path(atlas_root, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if slug:
        zim_fetch_progress_path(atlas_root).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def read_zim_fetch_progress(atlas_root: Path, pack_slug: str | None = None) -> dict[str, Any]:
    path = zim_fetch_progress_path(atlas_root, pack_slug)
    if not path.is_file():
        path = zim_fetch_progress_path(atlas_root)
    if not path.is_file():
        return {"downloaded": 0, "total": 0, "done": False, "status": "idle", "percent": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return _enrich_fetch_progress(data)
        return {"downloaded": 0, "total": 0, "done": False, "status": "idle", "percent": None}
    except (json.JSONDecodeError, OSError):
        return {"downloaded": 0, "total": 0, "done": False, "status": "error", "percent": None}


def request_cancel_zim_fetch(
    atlas_root: Path,
    pack_slug: str,
    *,
    pack_id: str | None = None,
) -> dict[str, Any]:
    slug = pack_slug.strip().lower()
    if not slug:
        return {"ok": False, "error": "pack_slug_required"}
    prog = read_zim_fetch_progress(atlas_root, slug)
    active_statuses = {"starting", "checking", "downloading", "warning"}
    active = _signal_fetch_cancel("zim", slug)
    if not active and prog.get("status") not in active_statuses:
        return {"ok": False, "error": "not_running", "status": prog.get("status") or "idle"}
    payload: dict[str, Any] = {
        "pack_slug": slug,
        "status": "cancelled",
        "done": True,
        "message": "Download cancelled",
    }
    if pack_id:
        payload["pack_id"] = pack_id
    if prog.get("downloaded"):
        payload["downloaded"] = prog["downloaded"]
    if prog.get("total"):
        payload["total"] = prog["total"]
    write_zim_fetch_progress(atlas_root, payload, slug)
    return {"ok": True, "status": "cancelled", "pack_slug": slug}


def _list_zim_files(target: Path) -> list[str]:
    if not target.is_dir():
        return []
    return sorted(p.name for p in target.rglob("*.zim") if p.is_file())


def _zim_fetch_config(manifest: dict[str, Any]) -> dict[str, Any]:
    meta = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
    cfg = meta.get("zim_fetch") if isinstance(meta.get("zim_fetch"), dict) else {}
    return dict(cfg)


def should_auto_fetch_zim(manifest: dict[str, Any], target: Path) -> bool:
    if os.environ.get("ATLAS_ZIM_SKIP_FETCH", "").strip() in {"1", "true", "yes"}:
        return False
    ptype = manifest.get("type") or ""
    if ptype not in {"atlas.content.knowledge", "atlas.content.education"}:
        return False
    if _list_zim_files(target):
        return False
    cfg = _zim_fetch_config(manifest)
    if not cfg:
        return False
    if cfg.get("enabled") is False:
        return False
    if cfg.get("url") or os.environ.get("ATLAS_ZIM_URL") or cfg.get("default_url"):
        return True
    return False


def fetch_zim_for_manifest(
    manifest: dict[str, Any],
    target: Path,
    atlas_root: Path,
    *,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Download a Kiwix ZIM into the pack target (and register via knowledge.index)."""
    meta = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
    cfg = _zim_fetch_config(manifest)
    slug = _pack_slug(manifest, target)
    url = (
        (os.environ.get("ATLAS_ZIM_URL") or "").strip()
        or str(cfg.get("url") or "").strip()
        or str(cfg.get("default_url") or "").strip()
        or DEFAULT_WIKIPEDIA_ZIM_URL
    )
    out_name = (
        (os.environ.get("ATLAS_ZIM_NAME") or "").strip()
        or str(cfg.get("filename") or "").strip()
        or DEFAULT_WIKIPEDIA_ZIM_NAME
    )
    if not out_name.lower().endswith(".zim"):
        out_name = f"{out_name}.zim"
    hint = int(cfg.get("size_hint_bytes") or meta.get("size_hint_bytes") or DEFAULT_WIKIPEDIA_ZIM_SIZE_HINT)
    licence = str(cfg.get("licence") or "CC-BY-SA-4.0")
    attribution = str(cfg.get("attribution") or "© Wikipedia contributors (Kiwix ZIM)")

    target.mkdir(parents=True, exist_ok=True)
    dest = target / out_name
    partial = dest.with_suffix(dest.suffix + ".partial")
    cancel_event, cancel_key = register_fetch_cancel("zim", slug, partials=[partial])

    def _cancelled() -> None:
        if partial.exists():
            partial.unlink(missing_ok=True)
        write_zim_fetch_progress(
            atlas_root,
            {
                "pack_id": manifest.get("id"),
                "pack_slug": slug,
                "status": "cancelled",
                "done": True,
                "message": "Download cancelled",
                "total": hint,
            },
            slug,
        )

    try:
        return _fetch_zim_for_manifest_body(
            manifest=manifest,
            target=target,
            atlas_root=atlas_root,
            slug=slug,
            url=url,
            out_name=out_name,
            hint=hint,
            licence=licence,
            attribution=attribution,
            dest=dest,
            meta=meta,
            progress_cb=progress_cb,
            cancel_event=cancel_event,
            _cancelled=_cancelled,
        )
    finally:
        unregister_fetch_cancel(cancel_key)


def _fetch_zim_for_manifest_body(
    *,
    manifest: dict[str, Any],
    target: Path,
    atlas_root: Path,
    slug: str,
    url: str,
    out_name: str,
    hint: int,
    licence: str,
    attribution: str,
    dest: Path,
    meta: dict[str, Any],
    progress_cb: Callable[[dict[str, Any]], None] | None,
    cancel_event: threading.Event,
    _cancelled: Callable[[], None],
) -> dict[str, Any]:
    if cancel_event.is_set():
        _cancelled()
        raise FetchCancelledError("download cancelled")

    def _progress(downloaded: int, total: int) -> None:
        data = {
            "pack_id": manifest.get("id"),
            "pack_slug": slug,
            "status": "downloading",
            "done": False,
            "downloaded": downloaded,
            "total": total or hint,
            "url": url,
            "filename": out_name,
            "licence": licence,
            "message": "Downloading Wikipedia ZIM…",
        }
        write_zim_fetch_progress(atlas_root, data, slug)
        if progress_cb:
            progress_cb(data)

    if hint >= LARGE_ZIM_WARN_BYTES:
        write_zim_fetch_progress(
            atlas_root,
            {
                "pack_id": manifest.get("id"),
                "pack_slug": slug,
                "status": "warning",
                "done": False,
                "downloaded": 0,
                "total": hint,
                "url": url,
                "filename": out_name,
                "message": f"Large ZIM (~{hint // (1024**3)}+ GiB estimated). Continuing…",
                "licence": licence,
            },
            slug,
        )

    write_zim_fetch_progress(
        atlas_root,
        {
            "pack_id": manifest.get("id"),
            "pack_slug": slug,
            "status": "checking",
            "done": False,
            "downloaded": 0,
            "total": hint,
            "url": url,
            "filename": out_name,
            "message": "Checking ZIM download URL…",
            "licence": licence,
        },
        slug,
    )
    if not _http_head_ok(url):
        raise PackError(f"ZIM URL not reachable: {url}")
    if cancel_event.is_set():
        _cancelled()
        raise FetchCancelledError("download cancelled")

    write_zim_fetch_progress(
        atlas_root,
        {
            "pack_id": manifest.get("id"),
            "pack_slug": slug,
            "status": "starting",
            "done": False,
            "downloaded": 0,
            "total": hint,
            "url": url,
            "filename": out_name,
            "message": "Starting ZIM download…",
            "licence": licence,
        },
        slug,
    )
    try:
        _download_url_to_file(url, dest, progress_cb=_progress, cancel_event=cancel_event)
    except FetchCancelledError:
        _cancelled()
        raise
    except PackError as e:
        raise PackError(str(e).replace("tile download failed", "ZIM download failed")) from e
    if cancel_event.is_set():
        _cancelled()
        raise FetchCancelledError("download cancelled")

    # Register with Kiwix immediately; Markdown RAG already indexed on install.
    language = str(meta.get("language") or "eng")
    registered = register_zim_with_kiwix(
        dest,
        atlas_root,
        title=str(manifest.get("name") or dest.stem),
        description=str(manifest.get("description") or ""),
        language=language,
    )
    size = dest.stat().st_size
    result = {
        "ok": True,
        "pack_id": manifest.get("id"),
        "pack_slug": slug,
        "path": str(dest),
        "kiwix_path": str(registered),
        "bytes": size,
        "url": url,
        "licence": licence,
        "attribution": attribution,
    }
    write_zim_fetch_progress(
        atlas_root,
        {
            "pack_id": manifest.get("id"),
            "pack_slug": slug,
            "status": "ready",
            "done": True,
            "downloaded": size,
            "total": size,
            "path": str(dest),
            "kiwix_path": str(registered),
            "licence": licence,
            "message": "ZIM ready offline (Kiwix)",
        },
        slug,
    )
    return result


def _expand_fetch_config(manifest: dict[str, Any]) -> dict[str, Any]:
    meta = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
    cfg = meta.get("expand_fetch") if isinstance(meta.get("expand_fetch"), dict) else {}
    return dict(cfg)


def should_auto_expand_content(manifest: dict[str, Any], target: Path) -> bool:
    """Optional second-stage curriculum/content bundle download (kids expand, etc.)."""
    if os.environ.get("ATLAS_CONTENT_SKIP_EXPAND", "").strip() in {"1", "true", "yes"}:
        return False
    cfg = _expand_fetch_config(manifest)
    if not cfg or cfg.get("enabled") is False:
        return False
    url = (os.environ.get("ATLAS_KIDS_EXPAND_URL") or cfg.get("url") or "").strip()
    return bool(url)


def content_expand_progress_path(atlas_root: Path, pack_slug: str | None = None) -> Path:
    root = Path(atlas_root) / "knowledge"
    root.mkdir(parents=True, exist_ok=True)
    if pack_slug:
        return root / f".expand-fetch-progress-{pack_slug}"
    return root / ".expand-fetch-progress"


def write_content_expand_progress(
    atlas_root: Path, payload: dict[str, Any], pack_slug: str | None = None
) -> None:
    data = _enrich_fetch_progress(payload)
    slug = pack_slug or data.get("pack_slug")
    if slug:
        data["pack_slug"] = slug
    path = content_expand_progress_path(atlas_root, slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    if slug:
        content_expand_progress_path(atlas_root).write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )


def read_content_expand_progress(atlas_root: Path, pack_slug: str | None = None) -> dict[str, Any]:
    path = content_expand_progress_path(atlas_root, pack_slug)
    if not path.is_file():
        path = content_expand_progress_path(atlas_root)
    if not path.is_file():
        return {"downloaded": 0, "total": 0, "done": False, "status": "idle", "percent": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return _enrich_fetch_progress(data)
        return {"downloaded": 0, "total": 0, "done": False, "status": "idle", "percent": None}
    except (json.JSONDecodeError, OSError):
        return {"downloaded": 0, "total": 0, "done": False, "status": "error", "percent": None}


def fetch_expand_bundle_for_manifest(
    manifest: dict[str, Any],
    target: Path,
    atlas_root: Path,
) -> dict[str, Any]:
    """Download an optional expand tarball/zip into the pack target and re-index Markdown."""
    cfg = _expand_fetch_config(manifest)
    slug = _pack_slug(manifest, target)
    url = (os.environ.get("ATLAS_KIDS_EXPAND_URL") or cfg.get("url") or "").strip()
    if not url:
        raise PackError("expand_fetch URL not configured (set meta.expand_fetch.url or ATLAS_KIDS_EXPAND_URL)")
    hint = int(cfg.get("size_hint_bytes") or 0)
    filename = str(cfg.get("filename") or "expand-bundle.tar.gz")
    target.mkdir(parents=True, exist_ok=True)
    archive = target / filename

    def _progress(downloaded: int, total: int) -> None:
        write_content_expand_progress(
            atlas_root,
            {
                "pack_id": manifest.get("id"),
                "pack_slug": slug,
                "status": "downloading",
                "done": False,
                "downloaded": downloaded,
                "total": total or hint,
                "message": "Downloading curriculum expand bundle…",
            },
            slug,
        )

    write_content_expand_progress(
        atlas_root,
        {
            "pack_id": manifest.get("id"),
            "pack_slug": slug,
            "status": "starting",
            "done": False,
            "downloaded": 0,
            "total": hint,
            "message": "Starting expand download…",
        },
        slug,
    )
    _download_url_to_file(url, archive, progress_cb=_progress)
    expand_dir = target / "expand"
    if expand_dir.exists():
        shutil.rmtree(expand_dir)
    expand_dir.mkdir(parents=True, exist_ok=True)
    name = filename.lower()
    try:
        if name.endswith(".zip"):
            import zipfile

            with zipfile.ZipFile(archive, "r") as zf:
                zf.extractall(expand_dir)
        else:
            with tarfile.open(archive, "r:*") as tar:
                tar.extractall(expand_dir)
    except (tarfile.TarError, OSError) as e:
        raise PackError(f"expand bundle extract failed: {e}") from e
    _workflow_knowledge_index(manifest, target, atlas_root)
    size = archive.stat().st_size
    write_content_expand_progress(
        atlas_root,
        {
            "pack_id": manifest.get("id"),
            "pack_slug": slug,
            "status": "ready",
            "done": True,
            "downloaded": size,
            "total": size,
            "path": str(expand_dir),
            "message": "Expand bundle indexed",
        },
        slug,
    )
    return {"ok": True, "pack_id": manifest.get("id"), "path": str(expand_dir), "bytes": size}


def _kiwix_library_path(atlas_root: Path) -> Path:
    return atlas_root / "kiwix" / "library.xml"


def register_zim_with_kiwix(
    zim_path: Path,
    atlas_root: Path,
    *,
    title: str | None = None,
    description: str | None = None,
    language: str = "eng",
) -> Path:
    """Copy a ZIM into /srv/atlas/kiwix and register it in library.xml."""
    kiwix = atlas_root / "kiwix"
    kiwix.mkdir(parents=True, exist_ok=True)
    dest = kiwix / zim_path.name
    if zim_path.resolve() != dest.resolve():
        shutil.copy2(zim_path, dest)

    import xml.etree.ElementTree as ET

    lib_path = _kiwix_library_path(atlas_root)
    if lib_path.is_file():
        try:
            tree = ET.parse(lib_path)
            root = tree.getroot()
        except ET.ParseError:
            root = ET.Element("library", version="20110515")
            tree = ET.ElementTree(root)
    else:
        root = ET.Element("library", version="20110515")
        tree = ET.ElementTree(root)

    # Remove existing book with same path/id
    for book in list(root.findall("book")):
        if book.get("path") == dest.name or book.get("id") == dest.stem:
            root.remove(book)

    book = ET.SubElement(root, "book")
    book.set("id", dest.stem)
    book.set("path", dest.name)
    book.set("title", title or dest.stem.replace("_", " "))
    book.set("description", description or "Offline ZIM knowledge pack")
    book.set("language", language)
    book.set("faviconMimeType", "image/png")
    tree.write(lib_path, encoding="utf-8", xml_declaration=True)
    return dest


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
    """Index pack payload into agent RAG and optionally register Kiwix ZIM books."""
    ingested = 0
    zims: list[str] = []
    meta = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
    language = str(meta.get("language") or "eng")

    if target.is_dir():
        # Register any .zim for offline browser (Kiwix); keep originals in pack target too.
        for zim in sorted(target.rglob("*.zim")):
            try:
                dest = register_zim_with_kiwix(
                    zim,
                    atlas_root,
                    title=str(manifest.get("name") or zim.stem),
                    description=str(manifest.get("description") or ""),
                    language=language,
                )
                zims.append(dest.name)
            except OSError:
                continue

        try:
            from knowledge_service import KnowledgeService, SUPPORTED_EXTENSIONS  # type: ignore
        except ImportError:
            SUPPORTED_EXTENSIONS = {".md", ".txt", ".markdown", ".html", ".htm", ".csv", ".json"}  # type: ignore
            KnowledgeService = None  # type: ignore

        if KnowledgeService is not None:
            ks = KnowledgeService(atlas_root / "knowledge")
            # Shared pack corpus — visible to all users via KnowledgeService shared search.
            user_id = "system"
            for path in sorted(target.rglob("*")):
                if not path.is_file():
                    continue
                if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                # Skip licence/attribution noise already handled separately
                if path.name.lower() in {"readme.txt", "licence.txt", "license.txt", "readme.md"}:
                    continue
                try:
                    ks.ingest_file(user_id, path, trust="pack")
                    ingested += 1
                except Exception:
                    pass
        else:
            # Dev/test fallback: copy text docs into knowledge/incoming for later ingest
            incoming = atlas_root / "knowledge" / "incoming" / str(manifest.get("id") or "pack")
            incoming.mkdir(parents=True, exist_ok=True)
            for path in sorted(target.rglob("*")):
                if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    try:
                        shutil.copy2(path, incoming / path.name)
                        ingested += 1
                    except OSError:
                        pass

    marker = {
        "pack_id": manifest.get("id"),
        "ingested_docs": ingested,
        "zim_books": zims,
        "indexed_at": time.time(),
    }
    if target.is_dir():
        (target / ".atlas-indexed").write_text(json.dumps(marker, indent=2) + "\n", encoding="utf-8")


def install_pack(
    pack_path: Path,
    atlas_root: Path = Path("/srv/atlas"),
    hooks: dict[str, Callable[..., None]] | None = None,
    *,
    fetch_tiles: bool | None = None,
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

            # Persist manifest beside payload so later tile-fetch/reindex can read meta.
            try:
                shutil.copy2(root / "manifest.json", target / "manifest.json")
            except OSError:
                pass

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

            result: dict[str, Any] = {"ok": True, **record, "tiles_status": "stub"}
            do_fetch = fetch_tiles
            if do_fetch is None:
                do_fetch = should_auto_fetch_map_tiles(manifest, target)
            elif do_fetch and has_usable_map_tiles(target):
                do_fetch = False
            if do_fetch and maps_skip_fetch_env():
                do_fetch = False
            if do_fetch:
                try:
                    tile_info = fetch_map_tiles_for_manifest(manifest, target, atlas_root)
                    if wf == "maps.reindex":
                        _workflow_maps_reindex(manifest, target, atlas_root)
                    result["tiles"] = tile_info
                    result["tiles_status"] = "ready" if has_usable_map_tiles(target) else "stub"
                except PackError as e:
                    result["tiles_fetch_error"] = str(e)
                    result["tiles_status"] = "stub"
                    write_maps_fetch_progress(
                        atlas_root,
                        {
                            "country": _country_code_from_manifest(manifest, target),
                            "status": "error",
                            "done": True,
                            "error": str(e),
                            "message": "Pack installed as stub; tile download failed",
                        },
                        _country_code_from_manifest(manifest, target),
                    )
            elif (manifest.get("type") or "") == "atlas.content.map":
                result["tiles_status"] = "ready" if has_usable_map_tiles(target) else "stub"

            # Sync ZIM / expand fetch when caller did not request async (fetch_tiles=False from CC).
            if fetch_tiles is not False and should_auto_fetch_zim(manifest, target):
                try:
                    zim_info = fetch_zim_for_manifest(manifest, target, atlas_root)
                    result["zim"] = zim_info
                    result["zim_status"] = "ready"
                except PackError as e:
                    result["zim_fetch_error"] = str(e)
                    result["zim_status"] = "stub"
                    write_zim_fetch_progress(
                        atlas_root,
                        {
                            "pack_id": manifest.get("id"),
                            "pack_slug": _pack_slug(manifest, target),
                            "status": "error",
                            "done": True,
                            "error": str(e),
                            "message": "Pack installed; ZIM download failed — retry from Content",
                        },
                        _pack_slug(manifest, target),
                    )
            elif _zim_fetch_config(manifest):
                result["zim_status"] = "ready" if _list_zim_files(target) else "pending"
            if fetch_tiles is not False and should_auto_expand_content(manifest, target):
                try:
                    expand_info = fetch_expand_bundle_for_manifest(manifest, target, atlas_root)
                    result["expand"] = expand_info
                    result["expand_status"] = "ready"
                except PackError as e:
                    result["expand_fetch_error"] = str(e)
                    result["expand_status"] = "stub"
            return result
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
    country = ""
    if target.name and re.fullmatch(r"[a-z]{2}", target.name.strip().lower()):
        country = target.name.strip().lower()
    if not country and "map" in str(match.get("type") or ""):
        country = str(pack_id or "").rsplit(".", 1)[-1].strip().lower()
        if not re.fullmatch(r"[a-z]{2}", country):
            country = ""
    if target.exists():
        shutil.rmtree(target) if target.is_dir() else target.unlink()
    # Drop stale fetch progress so reinstall cannot inherit a false "ready".
    if country:
        for p in (
            maps_fetch_progress_path(atlas_root, country),
            maps_fetch_progress_path(atlas_root),
        ):
            try:
                if not p.is_file():
                    continue
                if p.name == ".fetch-progress":
                    try:
                        g = json.loads(p.read_text(encoding="utf-8"))
                        if str((g or {}).get("country") or "").strip().lower() != country:
                            continue
                    except (json.JSONDecodeError, OSError, TypeError):
                        pass
                p.unlink(missing_ok=True)
            except OSError:
                pass
        registry_path = atlas_root / "maps" / "countries.json"
        if registry_path.is_file():
            try:
                registry = json.loads(registry_path.read_text(encoding="utf-8"))
                countries = registry.get("countries") if isinstance(registry, dict) else None
                if isinstance(countries, dict) and country in countries:
                    del countries[country]
                    registry["updated_at"] = time.time()
                    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
            except (json.JSONDecodeError, OSError, TypeError):
                pass
        try:
            sync_maps_to_nomad(atlas_root)
        except Exception:  # noqa: BLE001
            pass
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
    maps_registry: dict[str, Any] = {}
    registry_path = Path(atlas_root) / "maps" / "countries.json"
    if registry_path.is_file():
        try:
            raw = json.loads(registry_path.read_text(encoding="utf-8"))
            countries = raw.get("countries") if isinstance(raw, dict) else None
            if isinstance(countries, dict):
                maps_registry = countries
        except (json.JSONDecodeError, OSError):
            maps_registry = {}
    out = dict(catalogue)
    packs = []
    for entry in catalogue.get("packs") or []:
        row = dict(entry)
        inst = installed.get(entry.get("id", ""))
        row["installed"] = bool(inst)
        if inst:
            row["installed_version"] = inst.get("version")
            country = str(row.get("country") or "").strip().lower()
            if not country and inst.get("target"):
                country = Path(str(inst["target"])).name.strip().lower()
            if country and country in maps_registry:
                reg = maps_registry[country] or {}
                row["tiles_status"] = reg.get("status") or "stub"
                row["tiles"] = reg.get("tiles") or []
                # Filesystem wins when registry lags (stub) after a finished download.
                target = Path(str(inst.get("target") or reg.get("path") or ""))
                if row["tiles_status"] != "ready" and has_usable_map_tiles(target):
                    row["tiles_status"] = "ready"
                    row["tiles"] = _list_tile_files(target, usable_only=True)
            elif (row.get("category") == "maps") or "map" in str(row.get("type") or ""):
                target = Path(str(inst.get("target") or ""))
                row["tiles_status"] = "ready" if has_usable_map_tiles(target) else "stub"
            # Live fetch progress overrides registry when a download is in flight.
            # Never trust progress "ready" without usable tiles on disk (stale .fetch-progress).
            if country:
                target = Path(str(inst.get("target") or (maps_registry.get(country) or {}).get("path") or ""))
                prog = read_maps_fetch_progress(atlas_root, country)
                if prog.get("status") in {
                    "starting",
                    "preparing",
                    "downloading",
                    "extracting",
                    "finalizing",
                    "waiting",
                    "warning",
                    "running",
                } and not prog.get("done"):
                    row["tiles_status"] = "fetching"
                elif prog.get("status") == "ready" and prog.get("done"):
                    if has_usable_map_tiles(target):
                        row["tiles_status"] = "ready"
                        row["tiles"] = _list_tile_files(target, usable_only=True)
                    elif row.get("tiles_status") != "ready":
                        # Progress lies; keep stub/error so Open map stays honest.
                        row["tiles_status"] = "stub"
                elif prog.get("status") == "cancelled" and prog.get("done"):
                    row["tiles_status"] = "stub"
                elif prog.get("status") == "error" and prog.get("done") and row.get("tiles_status") != "ready":
                    row["tiles_status"] = "error"
            slug = str(row.get("id") or inst.get("id") or "").rsplit(".", 1)[-1].strip().lower()
            if slug:
                zprog = read_zim_fetch_progress(atlas_root, slug)
                if zprog.get("status") in {"starting", "checking", "downloading", "warning"} and not zprog.get("done"):
                    row["zim_status"] = "fetching"
                elif zprog.get("status") == "cancelled" and zprog.get("done"):
                    row["zim_status"] = "stub"
                elif zprog.get("status") == "ready" and zprog.get("done"):
                    row["zim_status"] = "ready"
                elif zprog.get("status") == "error" and zprog.get("done"):
                    row["zim_status"] = "error"
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
