#!/usr/bin/env python3
"""Arcalium OS package updates via APT (phase 1: atlas-* from signed/local repo).

Distinct from .atlas-update file-copy bundles — see docs/updates/OS_UPDATES.md.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

SCHEMA = "atlas.os_update/v1"
DEFAULT_REPO_ROOT = Path("/srv/atlas/apt-repo")
DEFAULT_STATE_FILE = Path("/srv/atlas/updates/os-status.json")
SOURCES_LIST = Path("/etc/apt/sources.list.d/atlas.list")
SOURCES_TEMPLATE = Path("/usr/share/atlas/apt/atlas.list.template")
KEYRING_PATH = Path("/usr/share/keyrings/atlas-archive-keyring.gpg")
KEYRING_README = Path("/usr/share/atlas/apt/KEYRING.md")

# Only atlas-* packages in phase 1. Full Debian upgrades are phase 2 + owner confirm.
ATLAS_PKG_GLOB = "atlas-*"
FULL_UPGRADE_ENV = "ATLAS_OS_ALLOW_FULL_UPGRADE"


class OsUpdateError(Exception):
    pass


@dataclass
class OsUpdateStatus:
    schema: str = SCHEMA
    ok: bool = True
    mode: str = "atlas_packages"  # atlas_packages | full_system (gated)
    source_configured: bool = False
    source_path: str | None = None
    keyring_present: bool = False
    repo_present: bool = False
    installed: list[dict[str, str]] = field(default_factory=list)
    upgradable: list[dict[str, str]] = field(default_factory=list)
    last_check: str | None = None
    last_apply: str | None = None
    detail: str = ""
    phase2_full_upgrade_documented: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run(
    cmd: list[str],
    *,
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    if runner is not None:
        return runner(cmd)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def discover_repo_roots(extra: list[Path] | None = None) -> list[Path]:
    """Local / USB apt-repo directories (must contain dists/ or Packages)."""
    candidates: list[Path] = [
        DEFAULT_REPO_ROOT,
        Path("/usr/share/atlas/apt-repo"),
    ]
    if extra:
        candidates.extend(extra)
    # Common USB mount layouts
    for base in (Path("/media"), Path("/mnt"), Path("/run/media")):
        if not base.is_dir():
            continue
        try:
            for user_dir in base.iterdir():
                if not user_dir.is_dir():
                    continue
                for mount in user_dir.iterdir():
                    candidates.append(mount / "atlas-apt-repo")
                    candidates.append(mount / "apt-repo")
        except OSError:
            continue
    out: list[Path] = []
    seen: set[str] = set()
    for p in candidates:
        try:
            key = str(p.resolve()) if p.exists() else str(p)
        except OSError:
            key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if _looks_like_repo(p):
            out.append(p)
    return out


def _looks_like_repo(path: Path) -> bool:
    if not path.is_dir():
        return False
    if (path / "dists").is_dir():
        return True
    if (path / "Packages").is_file() or (path / "Packages.gz").is_file():
        return True
    if (path / "pool").is_dir():
        return True
    return False


def source_configured() -> tuple[bool, str | None]:
    if SOURCES_LIST.is_file():
        text = SOURCES_LIST.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            s = line.strip()
            if s and not s.startswith("#"):
                return True, s
    return False, None


def list_installed_atlas(
    *,
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> list[dict[str, str]]:
    if not shutil.which("dpkg-query") and runner is None:
        return []
    proc = _run(
        ["dpkg-query", "-W", "-f=${Package}\\t${Version}\\t${Status}\\n", ATLAS_PKG_GLOB],
        runner=runner,
        timeout=60,
    )
    packages: list[dict[str, str]] = []
    if proc.returncode not in (0, 1):
        return packages
    for line in (proc.stdout or "").splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        name, version, status = parts[0], parts[1], parts[2]
        if "installed" not in status:
            continue
        packages.append({"name": name, "version": version})
    return packages


def parse_upgradable_lines(text: str, *, atlas_only: bool = True) -> list[dict[str, str]]:
    """Parse `apt list --upgradable` style output."""
    out: list[dict[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("Listing"):
            continue
        # name/suite version arch [upgradable from: old]
        m = re.match(
            r"^([a-z0-9][a-z0-9+.-]*)/[^\s]+\s+(\S+)\s+\S+\s+\[upgradable from:\s*([^\]]+)\]",
            line,
            re.I,
        )
        if not m:
            continue
        name, new_ver, old_ver = m.group(1), m.group(2), m.group(3).strip()
        if atlas_only and not name.startswith("atlas-"):
            continue
        out.append({"name": name, "from": old_ver, "to": new_ver})
    return out


def os_update_status(
    *,
    state_file: Path | None = None,
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> OsUpdateStatus:
    state_file = state_file or Path(
        os.environ.get("ATLAS_OS_UPDATE_STATE", str(DEFAULT_STATE_FILE))
    )
    configured, src = source_configured()
    repos = discover_repo_roots()
    st = OsUpdateStatus(
        source_configured=configured,
        source_path=src,
        keyring_present=KEYRING_PATH.is_file() and KEYRING_PATH.stat().st_size > 0,
        repo_present=bool(repos),
        installed=list_installed_atlas(runner=runner),
        detail="",
    )
    if repos and not st.detail:
        st.detail = f"local_repo:{repos[0]}"
    if state_file.is_file():
        try:
            prev = json.loads(state_file.read_text(encoding="utf-8"))
            st.last_check = prev.get("last_check")
            st.last_apply = prev.get("last_apply")
            if prev.get("upgradable"):
                st.upgradable = list(prev["upgradable"])
        except (json.JSONDecodeError, OSError):
            pass
    return st


def _write_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def check_os_updates(
    *,
    atlas_only: bool = True,
    refresh: bool = True,
    state_file: Path | None = None,
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    """apt update (optional) + list upgradable atlas-* packages."""
    state_file = state_file or Path(
        os.environ.get("ATLAS_OS_UPDATE_STATE", str(DEFAULT_STATE_FILE))
    )
    status = os_update_status(state_file=state_file, runner=runner)
    errors: list[str] = []

    if refresh:
        # Scoped refresh: still uses system apt, but we only *report* atlas-* later.
        proc = _run(["apt-get", "update", "-qq"], runner=runner, timeout=180)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
            errors.append(err[:800])

    list_proc = _run(
        ["apt", "list", "--upgradable"],
        runner=runner,
        timeout=120,
    )
    upgradable = parse_upgradable_lines(list_proc.stdout or "", atlas_only=atlas_only)
    if list_proc.returncode not in (0, 1) and not upgradable:
        err = (list_proc.stderr or list_proc.stdout or f"exit {list_proc.returncode}").strip()
        errors.append(err[:800])

    now = _utc_now()
    payload = {
        "schema": SCHEMA,
        "ok": not errors,
        "atlas_only": atlas_only,
        "upgradable": upgradable,
        "installed": status.installed,
        "source_configured": status.source_configured,
        "source_path": status.source_path,
        "keyring_present": status.keyring_present,
        "repo_present": status.repo_present,
        "last_check": now,
        "last_apply": status.last_apply,
        "errors": errors,
        "phase": 1,
        "phase2_note": (
            "Full Debian security upgrades are phase 2 — require owner confirm "
            "and ATLAS_OS_ALLOW_FULL_UPGRADE=1; not auto-run."
        ),
    }
    _write_state(
        state_file,
        {
            "last_check": now,
            "last_apply": status.last_apply,
            "upgradable": upgradable,
        },
    )
    return payload


def apply_os_updates(
    *,
    atlas_only: bool = True,
    full_system: bool = False,
    owner_confirmed: bool = False,
    dry_run: bool = False,
    state_file: Path | None = None,
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> dict[str, Any]:
    """Apply package upgrades. Full system upgrade is gated."""
    state_file = state_file or Path(
        os.environ.get("ATLAS_OS_UPDATE_STATE", str(DEFAULT_STATE_FILE))
    )

    if full_system:
        if not owner_confirmed:
            return {
                "ok": False,
                "error": "owner_confirmation_required",
                "detail": "Full OS upgrade requires explicit owner confirm.",
            }
        if os.environ.get(FULL_UPGRADE_ENV, "0") != "1":
            return {
                "ok": False,
                "error": "full_upgrade_disabled",
                "detail": (
                    f"Set {FULL_UPGRADE_ENV}=1 on the apply helper to allow "
                    "full-system apt upgrade (phase 2)."
                ),
            }
        cmd = ["apt-get", "upgrade", "-y"]
        if dry_run:
            cmd = ["apt-get", "upgrade", "--dry-run"]
        scope = "full_system"
    else:
        # Phase 1: only packages matching atlas-*
        check = check_os_updates(
            atlas_only=True,
            refresh=False,
            state_file=state_file,
            runner=runner,
        )
        names = [p["name"] for p in check.get("upgradable") or []]
        if not names:
            return {
                "ok": True,
                "action": "apply",
                "scope": "atlas_packages",
                "detail": "nothing_to_upgrade",
                "upgraded": [],
            }
        if dry_run:
            return {
                "ok": True,
                "action": "apply",
                "scope": "atlas_packages",
                "dry_run": True,
                "would_upgrade": names,
            }
        cmd = ["apt-get", "install", "--only-upgrade", "-y", *names]
        scope = "atlas_packages"

    proc = _run(cmd, runner=runner, timeout=900)
    ok = proc.returncode == 0
    now = _utc_now()
    out: dict[str, Any] = {
        "ok": ok,
        "action": "apply",
        "scope": scope,
        "detail": (proc.stdout or "")[-2000:] if ok else (proc.stderr or proc.stdout or "")[-2000:],
        "returncode": proc.returncode,
    }
    if ok:
        prev = {}
        if state_file.is_file():
            try:
                prev = json.loads(state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                prev = {}
        _write_state(
            state_file,
            {
                "last_check": prev.get("last_check"),
                "last_apply": now,
                "upgradable": [],
            },
        )
        out["last_apply"] = now
    else:
        out["error"] = "apt_failed"
    return out


def enable_local_source(
    repo_path: Path,
    *,
    write_sources: bool = True,
) -> dict[str, Any]:
    """Render atlas.list for a file:// repo (operator / privileged helper)."""
    repo_path = Path(repo_path)
    if not _looks_like_repo(repo_path):
        raise OsUpdateError(f"not_an_apt_repo: {repo_path}")
    uri = f"file:{repo_path.resolve()}"
    # Prefer signed keyring line when keyring exists; else document insecure local.
    if KEYRING_PATH.is_file() and KEYRING_PATH.stat().st_size > 0:
        line = (
            f"deb [signed-by={KEYRING_PATH}] {uri} atlas main\n"
        )
    else:
        # Local/USB MVP: trusted file repo until ceremony ships keyring.
        line = f"deb [trusted=yes] {uri} atlas main\n"
    body = (
        "# Managed by Arcalium OS updates (phase 1). See /usr/share/atlas/docs/OS_UPDATES.md\n"
        + line
    )
    if write_sources:
        SOURCES_LIST.parent.mkdir(parents=True, exist_ok=True)
        SOURCES_LIST.write_text(body, encoding="utf-8")
    return {"ok": True, "sources_list": str(SOURCES_LIST), "line": line.strip(), "written": write_sources}
