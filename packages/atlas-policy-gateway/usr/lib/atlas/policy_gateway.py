#!/usr/bin/env python3
"""Atlas Policy Gateway — capability tokens and approval gates."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

SIDE_EFFECT = {
    0: "auto",
    1: "scoped_logged",
    2: "preference_or_task",
    3: "explicit",
    4: "explicit_reauth",
}

PROHIBITED = {
    "shell.unrestricted",
    "docker.socket",
    "host.root_shell",
    "filesystem.delete_tree",
}


@dataclass
class ToolRegistration:
    tool_id: str
    side_effect: int
    required_capabilities: list[str]
    sandbox: str = "container"
    signed: bool = True


@dataclass
class PolicyGateway:
    tools: dict[str, ToolRegistration] = field(default_factory=dict)
    audit: list[dict[str, Any]] = field(default_factory=list)
    pending_approvals: dict[str, dict[str, Any]] = field(default_factory=dict)

    def register(self, tool: ToolRegistration) -> None:
        if tool.tool_id in PROHIBITED:
            raise ValueError(f"prohibited tool: {tool.tool_id}")
        self.tools[tool.tool_id] = tool

    def issue_token(self, capability: str, ttl_sec: int = 60) -> str:
        nonce = secrets.token_hex(8)
        exp = int(time.time()) + ttl_sec
        return f"cap:{capability}:{nonce}:{exp}"

    def evaluate(self, tool_id: str, agent_caps: set[str], user_approved: bool = False) -> dict[str, Any]:
        if tool_id in PROHIBITED:
            self._audit("deny", tool_id, "prohibited")
            return {"allow": False, "reason": "prohibited"}
        tool = self.tools.get(tool_id)
        if not tool:
            self._audit("deny", tool_id, "unregistered")
            return {"allow": False, "reason": "unregistered"}
        if not set(tool.required_capabilities).issubset(agent_caps):
            self._audit("deny", tool_id, "missing_capability")
            return {"allow": False, "reason": "missing_capability"}
        mode = SIDE_EFFECT[tool.side_effect]
        if mode == "auto":
            token = self.issue_token(tool.required_capabilities[0] if tool.required_capabilities else "tool")
            self._audit("allow", tool_id, "auto", token=token)
            return {"allow": True, "token": token, "approval": "auto"}
        if mode in {"explicit", "explicit_reauth"} and not user_approved:
            aid = secrets.token_hex(6)
            self.pending_approvals[aid] = {"tool_id": tool_id, "mode": mode}
            self._audit("pending", tool_id, mode, approval_id=aid)
            return {"allow": False, "pending_approval": aid, "mode": mode}
        token = self.issue_token(tool.required_capabilities[0] if tool.required_capabilities else "tool")
        self._audit("allow", tool_id, mode, token=token)
        return {"allow": True, "token": token, "approval": mode}

    def _audit(self, result: str, tool_id: str, reason: str, **extra: Any) -> None:
        self.audit.append({"result": result, "tool_id": tool_id, "reason": reason, **extra})


def default_gateway() -> PolicyGateway:
    gw = PolicyGateway()
    gw.register(ToolRegistration("knowledge.search", 0, ["knowledge.read"]))
    gw.register(ToolRegistration("documents.read", 1, ["documents.read"]))
    gw.register(ToolRegistration("notes.write", 2, ["notes.write"]))
    gw.register(ToolRegistration("network.fetch", 3, ["network.fetch"]))
    gw.register(ToolRegistration("system.health.read", 0, ["system.health.read"]))
    gw.register(ToolRegistration("network.mode.apply", 3, ["network.mode.apply"]))
    gw.register(ToolRegistration("backup.restore", 4, ["backup.restore"]))
    return gw


if __name__ == "__main__":
    gw = default_gateway()
    print(gw.evaluate("knowledge.search", {"knowledge.read"}))
    print(gw.evaluate("backup.restore", {"backup.restore"}))
    try:
        gw.register(ToolRegistration("shell.unrestricted", 4, ["root"]))
    except ValueError as e:
        print("blocked:", e)
