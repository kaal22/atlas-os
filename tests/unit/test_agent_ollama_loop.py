#!/usr/bin/env python3
"""Bounded agent task completes locally (dry-run / mocked Ollama)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "atlas-policy-gateway" / "usr" / "lib" / "atlas"))
sys.path.insert(0, str(ROOT / "packages" / "atlas-model-manager" / "usr" / "lib" / "atlas"))
sys.path.insert(0, str(ROOT / "packages" / "atlas-agent-runtime" / "usr" / "lib" / "atlas"))

os.environ["ATLAS_AGENT_DRY_RUN"] = "1"

from agent_runtime import AgentRuntime, AgentManifest  # noqa: E402
from memory_store import MemoryStore  # noqa: E402
from tool_registry import default_registry  # noqa: E402


def test_guide_completes_bounded_task():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        rt = AgentRuntime(
            dry_run=True,
            memory=MemoryStore(td_path / "memory"),
            tools=default_registry(notes_root=td_path / "notes"),
        )
        rt.register_agent(
            AgentManifest(
                id="atlas.guide",
                name="Atlas Guide",
                purpose="General assistant",
                tools=["knowledge.search", "notes.write"],
                capabilities=["knowledge.read", "notes.write"],
                memory_scopes=["session"],
                knowledge_scopes=["local"],
                approval_rules={},
                model_profile="tiny",
            )
        )
        task = rt.create_task("atlas.guide", "What is Atlas OS?", user_id="tester")
        rt.plan(task.id)
        result = rt.run_step(task.id)
        assert task.state == "completed", (task.state, result)
        assert result.get("answer"), result
        assert "Atlas Guide" in result["answer"] or "dry-run" in result["answer"]


def test_child_cannot_escalate_capabilities():
    rt = AgentRuntime(dry_run=True)
    rt.register_agent(
        AgentManifest(
            id="parent",
            name="Parent",
            purpose="p",
            tools=["knowledge.search"],
            capabilities=["knowledge.read"],
            memory_scopes=["session"],
            knowledge_scopes=["local"],
            approval_rules={},
        )
    )
    rt.register_agent(
        AgentManifest(
            id="child",
            name="Child",
            purpose="c",
            tools=["network.fetch"],
            capabilities=["knowledge.read", "network.fetch"],
            memory_scopes=["session"],
            knowledge_scopes=["local"],
            approval_rules={},
        )
    )
    parent = rt.create_task("parent", "hi")
    try:
        rt.create_task("child", "escalation", parent_id=parent.id)
        assert False, "expected PermissionError"
    except PermissionError as e:
        assert "escalation" in str(e)


def test_greeting_skips_knowledge_search():
    class FakeKnowledge:
        def search(self, user_id: str, query: str, limit: int = 5):
            return [
                {
                    "doc_id": "qm",
                    "name": "Quantum_mechanics.pdf",
                    "text": "Schrödinger equation and Hilbert spaces",
                    "score": 0.91,
                    "source": "vector",
                }
            ]

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        ks = FakeKnowledge()
        rt = AgentRuntime(
            dry_run=True,
            knowledge=ks,
            memory=MemoryStore(td_path / "memory"),
            tools=default_registry(knowledge=ks, notes_root=td_path / "notes"),
        )
        rt.register_agent(
            AgentManifest(
                id="atlas.guide",
                name="Atlas Guide",
                purpose="General assistant",
                tools=["knowledge.search", "notes.write"],
                capabilities=["knowledge.read", "notes.write"],
                memory_scopes=["session"],
                knowledge_scopes=["local"],
                approval_rules={},
                model_profile="tiny",
            )
        )
        task = rt.create_task("atlas.guide", "hello", user_id="tester")
        rt.plan(task.id)
        result = rt.run_step(task.id)
        assert task.state == "completed", (task.state, result)
        assert result.get("sources") == []
        assert "Quantum" not in (result.get("answer") or "")


if __name__ == "__main__":
    test_guide_completes_bounded_task()
    test_child_cannot_escalate_capabilities()
    test_greeting_skips_knowledge_search()
    print("OK test_agent_ollama_loop")
