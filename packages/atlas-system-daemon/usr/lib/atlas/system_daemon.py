#!/usr/bin/env python3
"""Atlas System Daemon v0 — privileged host ops over Unix socket.

Listens on /run/atlas/system.sock. Requires capability tokens issued by
Policy Gateway. Never exposes an internet listener.
"""
from __future__ import annotations

import json
import os
import socket
import socketserver
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SOCK_PATH = os.environ.get("ATLAS_SYSTEM_SOCK", "/run/atlas/system.sock")
AUDIT_LOG = Path(os.environ.get("ATLAS_AUDIT_LOG", "/srv/atlas/logs/system-daemon-audit.jsonl"))
ALLOWED = {
    "system.health.read",
    "system.power.profile.set",
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


def audit(event: dict[str, Any]) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    event = {**event, "ts": datetime.now(timezone.utc).isoformat()}
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def verify_token(token: str | None, capability: str) -> bool:
    """v0: accept tokens shaped as cap:<capability>:<nonce> from Policy Gateway."""
    if not token or not token.startswith("cap:"):
        return False
    parts = token.split(":")
    if len(parts) < 3:
        return False
    return parts[1] == capability or parts[1] == "*"


def handle(req: dict[str, Any]) -> dict[str, Any]:
    method = req.get("method")
    token = req.get("token")
    if method not in ALLOWED:
        audit({"result": "deny", "reason": "unknown_method", "method": method})
        return {"ok": False, "error": "unknown_method"}
    if not verify_token(token, method):
        audit({"result": "deny", "reason": "bad_token", "method": method})
        return {"ok": False, "error": "unauthorized"}

    if method == "system.health.read":
        services = {
            "ollama": Path("/usr/bin/ollama").exists(),
            "docker": Path("/var/run/docker.sock").exists(),
            "data": Path("/srv/atlas").exists(),
        }
        audit({"result": "allow", "method": method})
        return {"ok": True, "health": services, "status": "ok" if all(services.values()) or services["data"] else "degraded"}

    if method.startswith("container."):
        # v0 stubs — real docker ops gated; no arbitrary commands
        audit({"result": "allow", "method": method, "params": req.get("params", {})})
        return {"ok": True, "accepted": True, "method": method}

    audit({"result": "allow", "method": method})
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
