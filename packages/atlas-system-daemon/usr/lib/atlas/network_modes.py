#!/usr/bin/env python3
"""Atlas network mode controller — ufw helpers (product §23).

Canonical Command Centre listen port is 8787 (direct). atlas-proxy on :80 is
optional; firewall rules open 8787 for trusted LAN / mesh, never assume :80.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Literal

Mode = Literal["private_device", "trusted_lan", "private_hotspot", "offline_isolation"]

DEFAULT_MODE_FILE = Path("/etc/atlas/network-mode")
UFW_BIN = "/usr/sbin/ufw"


class UfwApplyError(RuntimeError):
    """Firewall apply failed; callers may soft-succeed after persisting intent."""

    def __init__(self, message: str, *, reason: str = "apply_failed", detail: str = "") -> None:
        super().__init__(message)
        self.reason = reason  # missing | inactive | apply_failed
        self.detail = detail or message


def ufw_binary() -> str | None:
    """Resolve ufw executable; prefer absolute path for systemd PATH."""
    if os.path.isfile(UFW_BIN) and os.access(UFW_BIN, os.X_OK):
        return UFW_BIN
    return shutil.which("ufw")


def ufw_status_text(ufw: str | None = None) -> tuple[str | None, str]:
    """Return (status_line_or_None, raw_output). status is 'active'/'inactive'/None."""
    bin_path = ufw or ufw_binary()
    if not bin_path:
        return None, "ufw not installed"
    try:
        proc = subprocess.run(
            [bin_path, "status"],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)
    raw = ((proc.stdout or "") + (proc.stderr or "")).strip()
    lower = raw.lower()
    if "status: active" in lower:
        return "active", raw
    if "status: inactive" in lower:
        return "inactive", raw
    return None, raw or f"exit {proc.returncode}"


def _commands_for(mode: Mode) -> list[list[str]]:
    """Return argv lists (not shell strings) for the given mode."""
    if mode == "private_device":
        return [
            ["--force", "reset"],
            ["default", "deny", "incoming"],
            ["default", "allow", "outgoing"],
            ["allow", "in", "on", "lo"],
            ["--force", "enable"],
        ]
    if mode == "trusted_lan":
        return [
            ["default", "deny", "incoming"],
            ["default", "allow", "outgoing"],
            ["allow", "in", "on", "lo"],
            ["allow", "from", "10.0.0.0/8", "to", "any", "port", "8787", "proto", "tcp"],
            ["allow", "from", "192.168.0.0/16", "to", "any", "port", "8787", "proto", "tcp"],
            ["allow", "from", "172.16.0.0/12", "to", "any", "port", "8787", "proto", "tcp"],
            ["--force", "enable"],
        ]
    if mode == "private_hotspot":
        return [
            ["default", "deny", "incoming"],
            ["allow", "in", "on", "lo"],
            ["allow", "in", "on", "atlas0", "to", "any", "port", "8787", "proto", "tcp"],
            ["--force", "enable"],
        ]
    if mode == "offline_isolation":
        return [
            ["--force", "reset"],
            ["default", "deny", "incoming"],
            ["default", "deny", "outgoing"],
            ["allow", "in", "on", "lo"],
            ["allow", "out", "on", "lo"],
            ["--force", "enable"],
        ]
    raise ValueError(mode)


def command_strings(mode: Mode) -> list[str]:
    """Human-readable command lines for dry-run / audit."""
    return ["ufw " + " ".join(args) for args in _commands_for(mode)]


def soft_fail_warning(mode: str, err: BaseException | str) -> str:
    """User-facing warning when mode intent is saved but firewall was not applied."""
    if isinstance(err, UfwApplyError):
        detail = (err.detail or str(err)).strip()
        if err.reason == "missing":
            return f"ufw not installed — mode saved ({mode}), firewall not applied"
        if err.reason == "inactive":
            base = f"ufw inactive — mode saved ({mode}), firewall not applied"
            if detail and "inactive" not in detail.lower() and detail != str(err):
                return f"{base}: {detail}"
            if detail and not detail.startswith("ufw inactive"):
                # Prefer raw ufw stderr when present
                if "failed" in detail.lower() or "error" in detail.lower():
                    return f"{base}: {detail}"
            return base
        return f"ufw apply failed — mode saved ({mode}), firewall not applied: {detail}"
    detail = str(err)
    lower = detail.lower()
    if "not installed" in lower or "not found" in lower or "not executable" in lower:
        return f"ufw not installed — mode saved ({mode}), firewall not applied"
    if "inactive" in lower:
        return f"ufw inactive — mode saved ({mode}), firewall not applied"
    return f"ufw apply failed — mode saved ({mode}), firewall not applied: {detail}"


def _run_ufw(ufw: str, args: list[str]) -> None:
    cmd = [ufw, *args]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError as e:
        raise UfwApplyError(
            f"ufw not found ({ufw}): {e}",
            reason="missing",
            detail=str(e),
        ) from e
    except subprocess.TimeoutExpired as e:
        raise UfwApplyError(
            f"ufw timed out: {' '.join(cmd)}",
            reason="apply_failed",
            detail=str(e),
        ) from e
    if proc.returncode == 0:
        return
    stderr = (proc.stderr or "").strip()
    stdout = (proc.stdout or "").strip()
    detail = stderr or stdout or f"exit {proc.returncode}"
    lower = detail.lower()
    reason = "inactive" if "inactive" in lower else "apply_failed"
    raise UfwApplyError(
        f"ufw {' '.join(args)} failed (exit {proc.returncode}): {detail}",
        reason=reason,
        detail=detail,
    )


def apply_mode(mode: Mode, dry_run: bool = True) -> list[str]:
    commands = command_strings(mode)
    if dry_run:
        return commands

    ufw = ufw_binary()
    if not ufw:
        raise UfwApplyError(
            "ufw not installed or not executable (/usr/sbin/ufw)",
            reason="missing",
            detail="ufw binary missing",
        )

    status, status_raw = ufw_status_text(ufw)
    # Still attempt apply when inactive — --force enable should activate.
    # If any step fails, include inactive context in the error.

    try:
        for args in _commands_for(mode):
            _run_ufw(ufw, args)
    except UfwApplyError as e:
        if status == "inactive" and e.reason != "missing":
            raise UfwApplyError(
                f"ufw inactive — apply failed: {e.detail}",
                reason="inactive",
                detail=e.detail or status_raw,
            ) from e
        raise
    return commands


def persist_mode(mode: str, path: Path | None = None) -> None:
    target = path or DEFAULT_MODE_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(mode + "\n", encoding="utf-8")


if __name__ == "__main__":
    for m in ("private_device", "trusted_lan", "private_hotspot", "offline_isolation"):
        print(m, apply_mode(m))  # type: ignore[arg-type]
