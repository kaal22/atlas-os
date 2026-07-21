#!/usr/bin/env python3
"""Atlas Updater — offline update bundles with snapshot + health-check rollback."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

ALLOWED_PAYLOAD_ROOTS = (
    Path("/usr/lib/atlas"),
    Path("/usr/share/atlas"),
    Path("/srv/atlas"),
    Path("/etc/atlas"),
)
SCHEMA = "atlas.update/v1"
VERSION_FILE = Path("/etc/atlas/version.json")
DEFAULT_UPDATE_ENDPOINT = "https://github.com/kaal22/atlas-os/releases/latest/download/channel.json"


def _update_endpoint() -> str:
    ep_file = Path("/etc/atlas/update-endpoint")
    if ep_file.is_file():
        val = ep_file.read_text(encoding="utf-8").strip()
        if val:
            return val
    return DEFAULT_UPDATE_ENDPOINT


def get_installed_version() -> dict[str, Any]:
    if VERSION_FILE.is_file():
        try:
            return json.loads(VERSION_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    conf = Path("/etc/atlas/atlas.conf")
    version = "0.0.0"
    if conf.is_file():
        for line in conf.read_text(encoding="utf-8").splitlines():
            if line.startswith("ATLAS_VERSION="):
                version = line.split("=", 1)[1].strip().strip('"')
                break
    return {"version": version, "channel": "stable", "updated_at": None}


def _write_version(version: str) -> None:
    data = get_installed_version()
    data["version"] = version
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    VERSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    VERSION_FILE.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


@dataclass
class UpdateResult:
    ok: bool
    action: str
    detail: str
    snapshot_id: str | None = None
    rolled_back: bool = False
    version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UpdateError(Exception):
    pass


def _allow_unsigned() -> bool:
    return os.environ.get("ATLAS_ALLOW_UNSIGNED", "0") == "1"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def verify_signature(manifest_path: Path, allowed_keys_dir: Path | None = None) -> bool:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not data.get("publisher"):
        return False
    if not str(data.get("digest", "")).startswith("sha256:"):
        return False
    sig = manifest_path.parent / "signature"
    checksums = manifest_path.parent / "checksums.sha256"
    if not sig.exists() or sig.read_text(encoding="utf-8").strip() == "DEV-UNSIGNED-PLACEHOLDER":
        return _allow_unsigned()
    keys = allowed_keys_dir or Path("/usr/share/atlas/keys")
    pub = keys / "atlas-dev-package.pub"
    if pub.is_file() and checksums.is_file() and shutil.which("openssl"):
        try:
            proc = subprocess.run(
                ["openssl", "dgst", "-sha256", "-verify", str(pub), "-signature", str(sig), str(checksums)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return proc.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False
    return _allow_unsigned()


def verify_checksums(bundle_root: Path) -> None:
    listing = bundle_root / "checksums.sha256"
    if not listing.exists():
        raise UpdateError("checksums.sha256 missing")
    for line in listing.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        digest, rel = parts[0], parts[1].strip()
        fpath = bundle_root / rel
        if not fpath.is_file():
            raise UpdateError(f"checksum target missing: {rel}")
        got = hashlib.sha256(fpath.read_bytes()).hexdigest()
        if got != digest:
            raise UpdateError(f"checksum mismatch: {rel}")


def _path_allowed(dest: Path, install_root: Path | None = None) -> bool:
    try:
        resolved = dest.resolve()
    except OSError:
        return False
    if install_root is not None:
        try:
            ir = install_root.resolve()
        except OSError:
            ir = install_root
        return str(resolved).startswith(str(ir))
    roots = list(ALLOWED_PAYLOAD_ROOTS)
    for root in roots:
        try:
            rr = root.resolve() if root.exists() else root
        except OSError:
            rr = root
        if str(resolved).startswith(str(rr)):
            return True
    return False


def create_dir_snapshot(
    paths: list[Path],
    snapshot_root: Path,
    label: str,
) -> Path:
    snap = snapshot_root / label
    if snap.exists():
        shutil.rmtree(snap)
    snap.mkdir(parents=True)
    meta = {"created": time.time(), "paths": []}
    for src in paths:
        if not src.exists():
            continue
        # Never snapshot whole trees like /usr/share/atlas — only leaf files.
        if src.is_dir():
            continue
        rel = str(src).lstrip("/")
        dest = snap / "tree" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        meta["paths"].append(str(src))
    (snap / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return snap


def restore_dir_snapshot(snap: Path) -> None:
    meta_path = snap / "meta.json"
    if not meta_path.is_file():
        raise UpdateError("snapshot_meta_missing")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    tree = snap / "tree"
    for raw in meta.get("paths") or []:
        src_orig = Path(raw)
        rel = str(src_orig).lstrip("/")
        bak = tree / rel
        if bak.is_file():
            src_orig.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bak, src_orig)
        elif src_orig.exists() and src_orig.is_file():
            # Was a new file with no prior snapshot — remove on rollback
            src_orig.unlink()


def create_snapshot(label: str, dry_run: bool = True, snapshot_root: Path | None = None) -> UpdateResult:
    root = snapshot_root or Path("/srv/atlas/snapshots")
    if dry_run:
        return UpdateResult(True, "snapshot", f"would snapshot to {root}/{label}", snapshot_id=label)
    root.mkdir(parents=True, exist_ok=True)
    create_dir_snapshot([], root, label)
    return UpdateResult(True, "snapshot", label, snapshot_id=label)


def rollback(label: str, dry_run: bool = True, snapshot_root: Path | None = None) -> UpdateResult:
    root = snapshot_root or Path("/srv/atlas/snapshots")
    snap = root / label
    if dry_run:
        return UpdateResult(True, "rollback", f"would restore {snap}", snapshot_id=label, rolled_back=True)
    restore_dir_snapshot(snap)
    return UpdateResult(True, "rollback", label, snapshot_id=label, rolled_back=True)


def run_health_checks(
    urls: list[str],
    timeout: float = 5.0,
    checker: Callable[[str], bool] | None = None,
) -> tuple[bool, list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    ok_all = True
    for url in urls:
        if checker is not None:
            good = checker(url)
            results.append({"url": url, "ok": good})
            if not good:
                ok_all = False
            continue
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                good = 200 <= getattr(resp, "status", 200) < 400
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            good = False
            results.append({"url": url, "ok": False, "error": str(e)})
            ok_all = False
            continue
        results.append({"url": url, "ok": good})
        if not good:
            ok_all = False
    return ok_all, results


def _write_diagnostics(log_dir: Path, payload: dict[str, Any]) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"update-{int(time.time())}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _extract_bundle(bundle_path: Path, td: Path) -> Path:
    if bundle_path.is_dir():
        return bundle_path
    if not bundle_path.is_file():
        raise UpdateError("bundle_not_found")
    with tarfile.open(bundle_path, "r:*") as tar:
        tar.extractall(td)
    if (td / "update.json").exists():
        return td
    candidates = list(td.rglob("update.json"))
    if not candidates:
        raise UpdateError("update.json missing")
    return candidates[0].parent


def _collect_touch_paths(manifest: dict[str, Any], payload_dir: Path, install_root: Path | None) -> list[Path]:
    """Existing destination files that will be overwritten (for snapshot)."""
    paths: list[Path] = []
    for f in payload_dir.rglob("*"):
        if not f.is_file():
            continue
        # Skip internal markers
        if f.name.startswith(".force-"):
            continue
        rel = f.relative_to(payload_dir).as_posix()
        if install_root is not None:
            dest = install_root / rel
        else:
            dest = Path("/") / rel
        if dest.is_file():
            paths.append(dest)
    for t in manifest.get("targets") or []:
        p = Path(t)
        if install_root is not None and str(p).startswith("/"):
            remapped = install_root / str(p).lstrip("/")
            if remapped.is_file():
                paths.append(remapped)
        elif p.is_file():
            paths.append(p)
    seen: set[str] = set()
    out: list[Path] = []
    for p in paths:
        key = str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def apply_update(
    bundle_path: Path,
    *,
    dry_run: bool = False,
    atlas_data: Path | None = None,
    install_root: Path | None = None,
    health_checker: Callable[[str], bool] | None = None,
    skip_health: bool = False,
) -> UpdateResult:
    """Apply an .atlas-update archive or extracted directory."""
    atlas_data = Path(atlas_data or os.environ.get("ATLAS_DATA", "/srv/atlas"))
    snapshot_root = atlas_data / "snapshots"
    log_dir = atlas_data / "logs"

    try:
        with tempfile.TemporaryDirectory() as td:
            try:
                root = _extract_bundle(Path(bundle_path), Path(td))
            except UpdateError as e:
                return UpdateResult(False, "apply", str(e))
            manifest_path = root / "update.json"
            if not manifest_path.exists():
                return UpdateResult(False, "apply", "missing update.json")
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            if data.get("schema") != SCHEMA:
                return UpdateResult(False, "apply", "bad schema")
            if not verify_signature(manifest_path):
                return UpdateResult(False, "apply", "signature verification failed")
            try:
                verify_checksums(root)
            except UpdateError as e:
                return UpdateResult(False, "apply", str(e))

            payload = root / "payload"
            if not payload.is_dir():
                return UpdateResult(False, "apply", "payload missing")

            version = str(data.get("to_version") or data.get("version") or "unknown")
            label = f"pre-update-{version}-{int(time.time())}"

            if dry_run:
                return UpdateResult(
                    True,
                    "apply",
                    f"would apply {version}",
                    snapshot_id=label,
                    version=version,
                )

            touch = _collect_touch_paths(data, payload, install_root)
            snap = create_dir_snapshot(touch, snapshot_root, label)
            # Track newly created files for rollback removal
            new_files: list[str] = []
            (snap / "new_files.json").write_text("[]", encoding="utf-8")

            applied: list[str] = []
            try:
                for f in payload.rglob("*"):
                    if not f.is_file():
                        continue
                    if f.name.startswith(".force-"):
                        continue
                    rel = f.relative_to(payload).as_posix()
                    if install_root is not None:
                        dest = install_root / rel
                    else:
                        dest = Path("/") / rel
                    if not _path_allowed(dest, install_root):
                        raise UpdateError(f"path_not_allowed: {dest}")
                    existed = dest.is_file()
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dest)
                    applied.append(str(dest))
                    if not existed:
                        new_files.append(str(dest))
                (snap / "new_files.json").write_text(json.dumps(new_files), encoding="utf-8")

                health_urls = list(data.get("health_urls") or [])
                if not health_urls and not skip_health:
                    health_urls = ["http://127.0.0.1:8787/"]

                if skip_health:
                    health_ok, health_results = True, []
                else:
                    if (payload / ".force-health-fail").exists() or data.get("force_health_fail"):
                        health_ok, health_results = False, [{"url": "forced", "ok": False}]
                    else:
                        health_ok, health_results = run_health_checks(health_urls, checker=health_checker)

                if not health_ok:
                    restore_dir_snapshot(snap)
                    for nf in new_files:
                        p = Path(nf)
                        if p.is_file():
                            p.unlink()
                    diag = _write_diagnostics(
                        log_dir,
                        {
                            "event": "update.rollback",
                            "version": version,
                            "snapshot_id": label,
                            "health": health_results,
                            "applied": applied,
                        },
                    )
                    return UpdateResult(
                        False,
                        "apply",
                        f"health check failed; rolled back (diag {diag})",
                        snapshot_id=label,
                        rolled_back=True,
                        version=version,
                    )

                _write_diagnostics(
                    log_dir,
                    {
                        "event": "update.commit",
                        "version": version,
                        "snapshot_id": label,
                        "health": health_results,
                        "applied": applied,
                    },
                )
                try:
                    _write_version(version)
                except OSError:
                    pass
                return UpdateResult(True, "apply", version, snapshot_id=label, version=version)
            except Exception as e:
                try:
                    restore_dir_snapshot(snap)
                    for nf in new_files:
                        p = Path(nf)
                        if p.is_file():
                            p.unlink()
                except Exception:
                    pass
                _write_diagnostics(
                    log_dir,
                    {"event": "update.error", "error": str(e), "snapshot_id": label, "version": version},
                )
                return UpdateResult(
                    False,
                    "apply",
                    str(e),
                    snapshot_id=label,
                    rolled_back=True,
                    version=version,
                )
    except Exception as e:
        return UpdateResult(False, "apply", f"unexpected: {e}")


def check_online_update(
    current_version: str | None = None,
    channel: str = "stable",
    endpoint: str | None = None,
) -> dict[str, Any] | None:
    """Fetch channel.json from update endpoint and return offer if newer, else None."""
    if current_version is None:
        current_version = get_installed_version().get("version", "0.0.0")
    url = endpoint or _update_endpoint()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AtlasUpdater/1"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError) as e:
        return {"error": "fetch_failed", "detail": str(e)}

    if data.get("schema") != "atlas.channel/v1":
        return {"error": "bad_schema"}

    latest = data.get("latest")
    if not latest:
        return None

    offered = latest.get("version", "")
    from_versions = latest.get("from_versions") or []
    if current_version == offered:
        return None
    if "*" not in from_versions and current_version not in from_versions:
        return {"error": "version_incompatible", "detail": f"installed {current_version} not in {from_versions}"}

    base_url = data.get("update_url_base", url.rsplit("/", 1)[0] + "/")
    bundle_url = base_url + (latest.get("bundle_filename") or "")
    return {
        "available": True,
        "version": offered,
        "current_version": current_version,
        "bundle_url": bundle_url,
        "bundle_sha256": latest.get("bundle_sha256", ""),
        "bundle_size": int(latest.get("bundle_size") or 0),
        "release_notes": latest.get("release_notes", ""),
        "published_at": latest.get("published_at", ""),
        "channel": data.get("channel", channel),
    }


def download_bundle(
    url: str,
    expected_sha256: str,
    dest_dir: Path,
    progress_cb: Any | None = None,
) -> Path:
    """Download bundle with resume support and hash verification."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = url.rsplit("/", 1)[-1] or "update.atlas-update"
    dest = dest_dir / filename
    partial = dest_dir / (filename + ".partial")

    existing_size = int(partial.stat().st_size) if partial.is_file() else 0
    headers: dict[str, str] = {"User-Agent": "AtlasUpdater/1"}
    if existing_size > 0:
        headers["Range"] = f"bytes={existing_size}-"

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=60) as resp:
            status = getattr(resp, "status", 200)
            if status == 200 and existing_size > 0:
                existing_size = 0
                mode = "wb"
            elif status == 206:
                mode = "ab"
            else:
                mode = "wb"
                existing_size = 0

            total = int(resp.headers.get("Content-Length") or 0) + existing_size
            downloaded = existing_size
            with partial.open(mode) as f:
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)
    except (urllib.error.URLError, OSError) as e:
        raise UpdateError(f"download_failed: {e}") from e

    got = sha256_file(partial).replace("sha256:", "")
    expected = expected_sha256.replace("sha256:", "")
    if expected and got != expected:
        partial.unlink(missing_ok=True)
        raise UpdateError(f"hash_mismatch: expected {expected[:16]}… got {got[:16]}…")

    partial.rename(dest)
    return dest


def read_bundle_metadata(bundle_path: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as td:
        root = _extract_bundle(Path(bundle_path), Path(td))
        data = json.loads((root / "update.json").read_text(encoding="utf-8"))
        notes = ""
        notes_path = root / "RELEASE_NOTES.txt"
        if notes_path.is_file():
            notes = notes_path.read_text(encoding="utf-8", errors="replace")[:8000]
        return {"manifest": data, "release_notes": notes, "path": str(bundle_path)}


def find_update_bundles(paths: list[str | Path]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in paths:
        base = Path(raw)
        if not base.exists():
            continue
        candidates = [base] if base.is_file() else list(base.rglob("*.atlas-update"))
        for f in candidates:
            if not f.is_file() or not str(f).endswith(".atlas-update"):
                continue
            key = str(f.resolve())
            if key in seen:
                continue
            seen.add(key)
            try:
                meta = read_bundle_metadata(f)
                m = meta["manifest"]
                found.append(
                    {
                        "path": key,
                        "from_version": m.get("from_version"),
                        "to_version": m.get("to_version"),
                        "publisher": m.get("publisher"),
                    }
                )
            except Exception:
                continue
    return found


def build_update_bundle(staging: Path, out_path: Path) -> str:
    """Write checksums + signature placeholder and pack as .atlas-update (tar.gz)."""
    manifest_path = staging / "update.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise UpdateError("bad schema")
    lines = []
    for f in sorted(staging.rglob("*")):
        if f.is_file() and f.name not in {"checksums.sha256", "signature"}:
            rel = f.relative_to(staging).as_posix()
            digest = hashlib.sha256(f.read_bytes()).hexdigest()
            lines.append(f"{digest}  {rel}")
    (staging / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (staging / "signature").write_text("DEV-UNSIGNED-PLACEHOLDER\n", encoding="utf-8")
    # update digest of whole archive after pack
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out_path, "w:gz") as tar:
        tar.add(staging, arcname=".")
    digest = sha256_file(out_path)
    data["digest"] = digest
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    # rebuild with updated digest in checksums
    lines = []
    for f in sorted(staging.rglob("*")):
        if f.is_file() and f.name not in {"checksums.sha256", "signature"}:
            rel = f.relative_to(staging).as_posix()
            lines.append(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {rel}")
    (staging / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with tarfile.open(out_path, "w:gz") as tar:
        tar.add(staging, arcname=".")
    digest = sha256_file(out_path)
    data["digest"] = digest
    manifest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    lines = []
    for f in sorted(staging.rglob("*")):
        if f.is_file() and f.name not in {"checksums.sha256", "signature"}:
            rel = f.relative_to(staging).as_posix()
            lines.append(f"{hashlib.sha256(f.read_bytes()).hexdigest()}  {rel}")
    (staging / "checksums.sha256").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with tarfile.open(out_path, "w:gz") as tar:
        tar.add(staging, arcname=".")
    return sha256_file(out_path)


if __name__ == "__main__":
    print(create_snapshot("test"))
    print(rollback("test"))
