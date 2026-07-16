#!/usr/bin/env python3
"""Capability escalation must fail closed (Phase 4 exit criterion)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "unit"))
sys.path.insert(0, str(ROOT / "packages" / "atlas-policy-gateway" / "usr" / "lib" / "atlas"))
sys.path.insert(0, str(ROOT / "packages" / "atlas-agent-runtime" / "usr" / "lib" / "atlas"))

from test_policy_levels import can_auto_run, is_prohibited  # noqa: E402
from policy_gateway import default_gateway, ToolRegistration, PROHIBITED  # noqa: E402
from agent_runtime import AgentRuntime, AgentManifest  # noqa: E402

os.environ["ATLAS_AGENT_DRY_RUN"] = "1"


def test_child_cannot_gain_shell():
    assert is_prohibited("host.root_shell")
    assert can_auto_run(4, "host.root_shell") is False


def test_level4_never_auto():
    assert can_auto_run(4, "backup.restore") is False


def test_prohibited_tools_denied_by_gateway():
    gw = default_gateway()
    for tid in PROHIBITED:
        d = gw.evaluate(tid, {"root", "knowledge.read"})
        assert d["allow"] is False
        assert d["reason"] == "prohibited"
    try:
        gw.register(ToolRegistration("shell.unrestricted", 4, ["root"]))
        assert False, "should not register prohibited"
    except ValueError:
        pass


def test_guide_cannot_apply_network_mode():
    gw = default_gateway()
    guide_caps = {"knowledge.read", "notes.write", "documents.read"}
    d = gw.evaluate("network.mode.apply", guide_caps)
    assert d["allow"] is False
    assert d["reason"] == "missing_capability"


def test_research_network_fetch_requires_approval():
    os.environ["ATLAS_AGENT_DRY_RUN"] = "1"
    rt = AgentRuntime(dry_run=True)
    rt.register_agent(
        AgentManifest(
            id="atlas.research",
            name="Research Agent",
            purpose="research",
            tools=["knowledge.search", "network.fetch"],
            capabilities=["knowledge.read", "network.fetch"],
            memory_scopes=["session"],
            knowledge_scopes=["local"],
            approval_rules={"network.fetch": "explicit"},
        )
    )
    task = rt.create_task("atlas.research", "Fetch https://example.com")
    rt.plan(task.id)
    # Force network.fetch path
    result = rt.run_step(task.id, force_tool="network.fetch")
    assert task.state == "awaiting_approval", (task.state, result)
    assert result.get("pending_approval")
    assert result.get("answer") is None


def test_guide_manifest_tool_not_on_manifest_denied():
    rt = AgentRuntime(dry_run=True)
    rt.register_agent(
        AgentManifest(
            id="atlas.guide",
            name="Atlas Guide",
            purpose="guide",
            tools=["knowledge.search"],
            capabilities=["knowledge.read"],
            memory_scopes=["session"],
            knowledge_scopes=["local"],
            approval_rules={},
        )
    )
    task = rt.create_task("atlas.guide", "pwn")
    agent = rt.agents["atlas.guide"]
    decision = rt._run_tool(task, agent, "network.fetch", {"url": "x"}, user_approved=True)
    assert decision.get("allow") is False
    assert decision.get("reason") == "tool_not_on_manifest"


if __name__ == "__main__":
    test_child_cannot_gain_shell()
    test_level4_never_auto()
    test_prohibited_tools_denied_by_gateway()
    test_guide_cannot_apply_network_mode()
    test_research_network_fetch_requires_approval()
    test_guide_manifest_tool_not_on_manifest_denied()
    print("OK test_capability_escalation")
