#!/usr/bin/env python3
"""Atlas System Daemon v0 — privileged host ops over Unix socket.

Listens on /run/atlas/system.sock. Requires capability tokens issued by
Policy Gateway. Never exposes an internet listener.
"""
from __future__ import annotations

import json
import os
import socketserver
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from network_modes import apply_mode, persist_mode  # noqa: E402

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
    "container.install",
    "container.start",
    "container.stop",
    "container.remove",
    "logs.bundle.create",
}

# Modes applied live with dry_run=False. Others remain dry-run unless owner confirms.
LIVE_MODES = {"private_device"}


def audit(event: dict[str, Any]) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    event = {**event, "ts": datetime.now(timezone.utc).isoformat(), "source": "system_daemon"}
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


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
            # Persist intent even if ufw cannot run under AF_UNIX hardening.
            persist_mode(mode, NETWORK_MODE_PATH)
            audit({
                "event": "network.mode.apply",
                "result": "fail",
                "mode": mode,
                "error": str(e),
                "persisted": True,
            })
            return {"ok": False, "error": str(e), "persisted": True, "mode": mode}

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
        return {"ok": True, "mode": mode, "dry_run": dry_run, "commands": commands}

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
