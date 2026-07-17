#!/usr/bin/env python3
"""Guide surfaces sources from knowledge hits; cross-user isolation holds."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "atlas-policy-gateway" / "usr" / "lib" / "atlas"))
sys.path.insert(0, str(ROOT / "packages" / "atlas-model-manager" / "usr" / "lib" / "atlas"))
sys.path.insert(0, str(ROOT / "packages" / "atlas-agent-runtime" / "usr" / "lib" / "atlas"))
sys.path.insert(0, str(ROOT / "packages" / "atlas-knowledge" / "usr" / "lib" / "atlas"))

os.environ["ATLAS_AGENT_DRY_RUN"] = "1"
os.environ["ATLAS_KNOWLEDGE_KEYWORD_ONLY"] = "1"

from agent_runtime import AgentRuntime, AgentManifest  # noqa: E402
from knowledge_service import KnowledgeService  # noqa: E402
from memory_store import MemoryStore  # noqa: E402
from tool_registry import default_registry  # noqa: E402


def test_ask_returns_sources_for_owner_only():
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        ks = KnowledgeService(td_path / "kb", keyword_only=True)
        doc = td_path / "notes.md"
        doc.write_text("The Crimson Orchid protocol uses keystone widgets.", encoding="utf-8")
        ks.ingest_file("alice", doc)

        rt = AgentRuntime(
            dry_run=True,
            memory=MemoryStore(td_path / "memory"),
            tools=default_registry(notes_root=td_path / "notes", knowledge=ks),
            knowledge=ks,
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
        task = rt.create_task("atlas.guide", "What uses keystone widgets?", user_id="alice")
        rt.plan(task.id)
        result = rt.run_step(task.id)
        assert task.state == "completed", (task.state, result)
        assert result.get("sources"), result
        assert any("Orchid" in (s.get("text") or "") for s in result["sources"])

        # Bob must not get Alice's hits via the same tool path
        task_b = rt.create_task("atlas.guide", "What uses keystone widgets?", user_id="bob")
        rt.plan(task_b.id)
        result_b = rt.run_step(task_b.id)
        assert not (result_b.get("sources") or []), result_b


if __name__ == "__main__":
    test_ask_returns_sources_for_owner_only()
    print("OK test_knowledge_citations")
