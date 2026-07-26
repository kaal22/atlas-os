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
                name="Arcalium Guide",
                purpose="General assistant",
                tools=["knowledge.search", "notes.write"],
                capabilities=["knowledge.read", "notes.write"],
                memory_scopes=["session"],
                knowledge_scopes=["local"],
                approval_rules={},
                model_profile="tiny",
            )
        )
        task = rt.create_task("atlas.guide", "What is Arcalium OS?", user_id="tester")
        rt.plan(task.id)
        result = rt.run_step(task.id)
        assert task.state == "completed", (task.state, result)
        assert result.get("answer"), result
        assert "Arcalium Guide" in result["answer"] or "dry-run" in result["answer"]


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
                name="Arcalium Guide",
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


def test_capability_meta_skips_knowledge_search():
    from agent_runtime import _should_auto_knowledge_search

    assert _should_auto_knowledge_search("i want to test your capabilities") is False
    assert _should_auto_knowledge_search("what can you do?") is False
    assert _should_auto_knowledge_search("Solar System planets") is True

    class FakeKnowledge:
        def search(self, user_id: str, query: str, limit: int = 5):
            return [
                {
                    "doc_id": "ctrl",
                    "name": "manifest.json",
                    "path": "/srv/atlas/knowledge/packs/wiki/manifest.json",
                    "text": "Wikipedia English mini ZIM size_class large extracted 0",
                    "score": 3.0,
                    "source": "keyword",
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
                id="atlas.research",
                name="Research Agent",
                purpose="Source-linked research",
                tools=["knowledge.search", "documents.read"],
                capabilities=["knowledge.read", "documents.read"],
                memory_scopes=["session"],
                knowledge_scopes=["local"],
                approval_rules={},
                model_profile="tiny",
            )
        )
        task = rt.create_task(
            "atlas.research",
            "i want to test your capabilities",
            user_id="tester",
        )
        rt.plan(task.id)
        result = rt.run_step(task.id)
        assert task.state == "completed", (task.state, result)
        assert result.get("sources") == []
        assert "manifest" not in (result.get("answer") or "").lower()
        assert "zim" not in (result.get("answer") or "").lower()


def test_control_file_hits_filtered_from_sources():
    class FakeKnowledge:
        def search(self, user_id: str, query: str, limit: int = 5):
            return [
                {
                    "doc_id": "ctrl",
                    "name": ".atlas-zim-rag.json",
                    "path": "/srv/atlas/knowledge/packs/wiki/extracted/.atlas-zim-rag.json",
                    "text": "extracted 0 processed 0 pack_id atlas.knowledge.wikipedia-en",
                    "score": 4.0,
                    "source": "keyword",
                },
                {
                    "doc_id": "good",
                    "name": "Solar_System.md",
                    "path": "/srv/atlas/knowledge/packs/wiki/articles/Solar_System.md",
                    "text": "The Solar System includes the Sun and eight planets.",
                    "score": 2.0,
                    "source": "keyword",
                },
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
                id="atlas.research",
                name="Research Agent",
                purpose="Source-linked research",
                tools=["knowledge.search"],
                capabilities=["knowledge.read"],
                memory_scopes=["session"],
                knowledge_scopes=["local"],
                approval_rules={},
                model_profile="tiny",
            )
        )
        task = rt.create_task("atlas.research", "Tell me about the Solar System", user_id="tester")
        rt.plan(task.id)
        result = rt.run_step(task.id)
        assert task.state == "completed", (task.state, result)
        names = [s.get("name") for s in (result.get("sources") or [])]
        assert ".atlas-zim-rag.json" not in names
        assert "Solar_System.md" in names


if __name__ == "__main__":
    test_guide_completes_bounded_task()
    test_child_cannot_escalate_capabilities()
    test_greeting_skips_knowledge_search()
    test_capability_meta_skips_knowledge_search()
    test_control_file_hits_filtered_from_sources()
    print("OK test_agent_ollama_loop")
