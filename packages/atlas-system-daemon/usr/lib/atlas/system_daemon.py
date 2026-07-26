#!/usr/bin/env python3
"""Atlas System Daemon v0 — privileged host ops over Unix socket.

Listens on /run/atlas/system.sock. Requires capability tokens issued by
Policy Gateway. Never exposes an internet listener.
"""
from __future__ import annotations

import json
import os
import socketserver
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from network_modes import apply_mode, persist_mode, soft_fail_warning  # noqa: E402

SOCK_PATH = os.environ.get("ATLAS_SYSTEM_SOCK", "/run/atlas/system.sock")
AUDIT_LOG = Path(os.environ.get("ATLAS_AUDIT_LOG", "/srv/atlas/logs/atlas-audit.jsonl"))
NETWORK_MODE_PATH = Path(os.environ.get("ATLAS_NETWORK_MODE_FILE", "/etc/atlas/network-mode"))

ALLOWED = {
    "system.health.read",
    "system.power.profile.set",
    "network.mode.apply",
    "network.mode.read",
    "network.hotspot.enable",
    "network.hotspot.disable",
    "storage.mount",
    "storage.unmount",
    "backup.create",
    "backup.restore",
    "update.stage",
    "update.apply",
    "update.rollback",
    "update.os.status",
    "update.os.check",
    "update.os.apply",
    "update.os.enable-source",
    "container.install",
    "container.start",
    "container.stop",
    "container.remove",
    "logs.bundle.create",
}

# Helpers live next to this module on the installed image; fall back for source-tree runs.
APPLY_HELPER = Path("/usr/lib/atlas/atlas-apply-update.py")
OS_APT_HELPER = Path("/usr/lib/atlas/atlas-os-apt.py")
APPLY_RESULT = Path("/srv/atlas/updates/staging/.apply-result.json")
OS_APPLY_RESULT = Path("/srv/atlas/updates/staging/.os-apply-result.json")
ALLOWED_OS_SOURCE_PREFIXES = (
    "/srv/atlas/",
    "/usr/share/atlas/",
    "/media/",
    "/mnt/",
    "/run/media/",
)

# Modes applied live with dry_run=False. Others remain dry-run unless owner confirms.
LIVE_MODES = {"private_device"}


def audit(event: dict[str, Any]) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    event = {**event, "ts": datetime.now(timezone.utc).isoformat(), "source": "system_daemon"}
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def _resolve_helper(primary: Path, *fallbacks: Path) -> Path | None:
    for candidate in (primary, *fallbacks):
        if candidate.is_file():
            return candidate
    # Source-tree layout: packages/atlas-system-daemon/usr/lib/atlas → packages/
    packages_root = Path(__file__).resolve().parents[4]
    repo_upd = packages_root / "atlas-updater" / "usr" / "lib" / "atlas"
    for name in (primary.name, *(p.name for p in fallbacks)):
        cand = repo_upd / name
        if cand.is_file():
            return cand
    return None


def _parse_helper_stdout(stdout: str) -> dict[str, Any] | None:
    out = (stdout or "").strip()
    if not out:
        return None
    # Prefer last JSON object line (helpers may print progress then JSON).
    for line in reversed(out.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return None


def _run_privileged_helper(
    helper: Path,
    args: list[str],
    *,
    result_file: Path,
    timeout_sec: int,
) -> dict[str, Any]:
    """Run update helper outside ProtectSystem=strict via systemd-run.

    Command Centre must not import subprocess; the daemon owns this boundary.
    """
    result_file.unlink(missing_ok=True)
    cmd = [
        "systemd-run",
        "--wait",
        "--collect",
        "--pipe",
        "-p",
        "ProtectSystem=false",
        "-p",
        "ProtectHome=false",
        "/usr/bin/python3",
        str(helper),
        *args,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "helper timed out"}
    except OSError as e:
        # Dev environments without systemd-run: run helper directly.
        try:
            proc = subprocess.run(
                ["/usr/bin/python3", str(helper), *args],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
            )
        except Exception as e2:
            return {"ok": False, "error": f"helper spawn failed: {e}; {e2}"}

    body: dict[str, Any] | None = None
    if result_file.is_file():
        try:
            body = json.loads(result_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            body = None
    if body is None:
        body = _parse_helper_stdout(proc.stdout or "")
    if body is None:
        err = (proc.stderr or "").strip() or f"helper exited {proc.returncode}"
        return {"ok": False, "error": err}
    return body


def _os_source_allowed(repo: str) -> bool:
    try:
        resolved = str(Path(repo).resolve())
    except OSError:
        resolved = repo
    return any(resolved.startswith(p) for p in ALLOWED_OS_SOURCE_PREFIXES)


def verify_token(token: str | None, capability: str) -> bool:
    """Accept tokens shaped as cap:<capability>:<nonce>[:exp] from Policy Gateway.

    Expiry (when present) is enforced; missing exp is allowed for legacy v0 tokens.
    """
    if not token or not token.startswith("cap:"):
        return False
    parts = token.split(":")
    if len(parts) < 3:
        return False
    if parts[1] != capability and parts[1] != "*":
        return False
    if len(parts) >= 4:
        try:
            exp = int(parts[3])
        except ValueError:
            return False
        if exp < int(time.time()):
            return False
    return True


def read_persisted_mode() -> str | None:
    if not NETWORK_MODE_PATH.exists():
        return None
    return NETWORK_MODE_PATH.read_text(encoding="utf-8").strip() or None


def handle(req: dict[str, Any]) -> dict[str, Any]:
    method = req.get("method")
    token = req.get("token")
    params = req.get("params") or {}

    if method not in ALLOWED:
        audit({"event": "privileged", "result": "deny", "reason": "unknown_method", "method": method})
        return {"ok": False, "error": "unknown_method"}
    if not verify_token(token, method):
        audit({"event": "privileged", "result": "deny", "reason": "bad_token", "method": method})
        return {"ok": False, "error": "unauthorized"}

    if method == "system.health.read":
        services = {
            "ollama": Path("/usr/bin/ollama").exists(),
            "docker": Path("/var/run/docker.sock").exists(),
            "data": Path("/srv/atlas").exists(),
        }
        audit({"event": "privileged", "result": "allow", "method": method})
        return {
            "ok": True,
            "health": services,
            "status": "ok" if all(services.values()) or services["data"] else "degraded",
        }

    if method == "network.mode.read":
        mode = read_persisted_mode() or "private_device"
        audit({"event": "privileged", "result": "allow", "method": method, "mode": mode})
        return {"ok": True, "mode": mode}

    if method == "network.mode.apply":
        mode = params.get("mode", "private_device")
        role = params.get("role", "")
        owner_confirmed = bool(params.get("owner_confirmed"))
        force_dry = bool(params.get("dry_run", False))

        if mode not in {"private_device", "trusted_lan", "private_hotspot", "offline_isolation"}:
            audit({"event": "network.mode.apply", "result": "deny", "reason": "bad_mode", "mode": mode})
            return {"ok": False, "error": "invalid_mode"}

        # Non-private: dry-run unless owner role + confirmation stub.
        if mode not in LIVE_MODES:
            if force_dry or not (role == "owner" and owner_confirmed):
                commands = apply_mode(mode, dry_run=True)  # type: ignore[arg-type]
                audit({
                    "event": "network.mode.apply",
                    "result": "dry_run" if force_dry or role != "owner" else "deny",
                    "method": method,
                    "mode": mode,
                    "role": role,
                    "commands": commands,
                })
                if force_dry:
                    return {"ok": True, "dry_run": True, "mode": mode, "commands": commands}
                if role != "owner" or not owner_confirmed:
                    return {"ok": False, "error": "owner_confirmation_required", "dry_run_only": True,
                            "commands": commands}

        dry_run = force_dry
        if mode not in LIVE_MODES and not (role == "owner" and owner_confirmed):
            dry_run = True

        try:
            commands = apply_mode(mode, dry_run=dry_run)  # type: ignore[arg-type]
        except Exception as e:
            # Persist intent even if ufw missing/inactive/sandbox-blocked.
            # Wizard and setup must not hard-fail on firewall apply.
            persist_mode(mode, NETWORK_MODE_PATH)
            err = str(e)
            warning = soft_fail_warning(mode, e)
            audit({
                "event": "network.mode.apply",
                "result": "deferred",
                "mode": mode,
                "error": err,
                "warning": warning,
                "persisted": True,
            })
            if not dry_run:
                return {
                    "ok": True,
                    "mode": mode,
                    "persisted": True,
                    "applied": False,
                    "deferred": True,
                    "warning": warning,
                    "error_detail": err,
                }
            return {
                "ok": True,
                "mode": mode,
                "dry_run": True,
                "persisted": True,
                "applied": False,
                "deferred": True,
                "warning": warning,
                "error_detail": err,
            }

        if not dry_run:
            persist_mode(mode, NETWORK_MODE_PATH)
        elif mode == "private_device":
            # Always persist private_device intent when requested.
            persist_mode(mode, NETWORK_MODE_PATH)

        audit({
            "event": "network.mode.apply",
            "result": "allow",
            "method": method,
            "mode": mode,
            "dry_run": dry_run,
            "commands": commands,
        })
        return {
            "ok": True,
            "mode": mode,
            "dry_run": dry_run,
            "commands": commands,
            "applied": not dry_run,
            "persisted": (not dry_run) or mode == "private_device",
        }

    if method == "update.apply":
        raw_path = str(params.get("path") or "")
        if not raw_path:
            return {"ok": False, "error": "path_required"}
        bundle = Path(raw_path)
        if not str(bundle).endswith(".atlas-update"):
            audit({"event": "update.apply", "result": "deny", "reason": "path_not_allowed"})
            return {"ok": False, "error": "path_not_allowed"}
        if not bundle.is_file():
            return {"ok": False, "error": "bundle_not_found"}
        helper = _resolve_helper(APPLY_HELPER, HERE / "atlas-apply-update.py")
        if helper is None:
            return {"ok": False, "error": "apply_helper_missing"}
        body = _run_privileged_helper(
            helper,
            [str(bundle)],
            result_file=APPLY_RESULT,
            timeout_sec=int(params.get("timeout_sec") or 600),
        )
        audit({
            "event": "update.apply",
            "result": "allow" if body.get("ok") else "fail",
            "path": str(bundle),
            "ok": bool(body.get("ok")),
            "rolled_back": body.get("rolled_back"),
            "version": body.get("version"),
        })
        if not body.get("ok") and "error" not in body:
            body["error"] = body.get("detail") or "apply failed"
        return body

    if method.startswith("update.os."):
        # Daemon ProtectSystem=strict cannot mutate apt state in-process;
        # one-shot systemd-run relaxes ProtectSystem for atlas-os-apt.py only.
        helper = _resolve_helper(OS_APT_HELPER, HERE / "atlas-os-apt.py")
        if helper is None:
            return {"ok": False, "error": "os_apt_helper_missing"}

        if method == "update.os.check":
            helper_args = ["check"]
        elif method == "update.os.enable-source":
            repo = str(params.get("path") or params.get("repo") or "").strip()
            if not repo:
                return {"ok": False, "error": "path_required"}
            if not _os_source_allowed(repo):
                audit({"event": "update.os", "result": "deny", "reason": "path_not_allowed", "path": repo})
                return {"ok": False, "error": "path_not_allowed"}
            try:
                resolved = str(Path(repo).resolve())
            except OSError:
                resolved = repo
            helper_args = ["enable-source", resolved]
        elif method == "update.os.apply":
            full = bool(params.get("full_system"))
            confirmed = bool(params.get("owner_confirmed"))
            dry = bool(params.get("dry_run"))
            if full and not confirmed:
                return {
                    "ok": False,
                    "error": "owner_confirmation_required",
                    "detail": "Full OS upgrade requires owner_confirmed=true.",
                }
            helper_args = ["apply"]
            if full:
                helper_args.append("--full")
            if confirmed:
                helper_args.append("--owner-confirmed")
            if dry:
                helper_args.append("--dry-run")
        elif method == "update.os.status":
            helper_args = ["status"]
        else:
            return {"ok": False, "error": "unknown_method"}

        body = _run_privileged_helper(
            helper,
            helper_args,
            result_file=OS_APPLY_RESULT,
            timeout_sec=int(params.get("timeout_sec") or 900),
        )
        audit({
            "event": "update.os",
            "result": "allow" if body.get("ok", True) else "fail",
            "method": method,
            "ok": bool(body.get("ok", True)),
            "scope": body.get("scope"),
        })
        return body

    if method.startswith("container."):
        audit({"event": "privileged", "result": "allow", "method": method, "params": params})
        return {"ok": True, "accepted": True, "method": method}

    audit({"event": "privileged", "result": "allow", "method": method})
    return {"ok": True, "accepted": True, "method": method}


class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        data = self.rfile.readline()
        if not data:
            return
        try:
            req = json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            self.wfile.write(b'{"ok":false,"error":"bad_json"}\n')
            return
        resp = handle(req)
        self.wfile.write((json.dumps(resp) + "\n").encode("utf-8"))


def main() -> int:
    Path(SOCK_PATH).parent.mkdir(parents=True, exist_ok=True)
    if Path(SOCK_PATH).exists():
        Path(SOCK_PATH).unlink()
    with socketserver.UnixStreamServer(SOCK_PATH, Handler) as server:
        os.chmod(SOCK_PATH, 0o660)
        print(f"atlas-system-daemon listening on {SOCK_PATH}", flush=True)
        server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
