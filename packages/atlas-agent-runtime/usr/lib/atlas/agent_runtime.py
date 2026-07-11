#!/usr/bin/env python3
"""Atlas Agent Runtime — manifests, task FSM, bounded execution."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pathlib import Path as _P
import sys

# Allow importing sibling packages when running from source tree
_HERE = _P(__file__).resolve().parent
_PACKAGES = _HERE.parents[3] if len(_HERE.parents) >= 4 else _P("/usr")
for rel in (
    _PACKAGES / "atlas-policy-gateway" / "usr" / "lib" / "atlas",
    _P("/usr/lib/atlas"),
    _HERE,
):
    if rel.exists():
        sys.path.insert(0, str(rel))

try:
    from policy_gateway import PolicyGateway, default_gateway
except ImportError:
    PolicyGateway = Any  # type: ignore

    def default_gateway():  # type: ignore
        raise RuntimeError("policy_gateway missing")

TRANSITIONS = {
    "draft": {"planned", "cancelled"},
    "planned": {"awaiting_approval", "queued", "cancelled"},
    "awaiting_approval": {"queued", "cancelled", "draft"},
    "queued": {"running", "cancelled"},
    "running": {"waiting_for_user", "paused", "completed", "failed", "cancelled"},
    "waiting_for_user": {"running", "cancelled", "failed"},
    "paused": {"running", "cancelled"},
    "completed": {"rolled_back"},
    "failed": {"draft", "rolled_back"},
    "cancelled": set(),
    "rolled_back": set(),
}


@dataclass
class AgentManifest:
    id: str
    name: str
    purpose: str
    tools: list[str]
    capabilities: list[str]
    memory_scopes: list[str]
    knowledge_scopes: list[str]
    approval_rules: dict[str, Any]
    model_profile: str = "light"
    publisher: str = "atlas"
    version: str = "1.0.0"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentManifest":
        return cls(
            id=data["id"],
            name=data["name"],
            purpose=data["purpose"],
            tools=data.get("tools", []),
            capabilities=data.get("capabilities", []),
            memory_scopes=data.get("memory_scopes", []),
            knowledge_scopes=data.get("knowledge_scopes", []),
            approval_rules=data.get("approval_rules", {}),
            model_profile=data.get("model_profile", "light"),
            publisher=data.get("publisher", "atlas"),
            version=data.get("version", "1.0.0"),
        )


@dataclass
class Task:
    id: str
    agent_id: str
    prompt: str
    state: str = "draft"
    plan: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    parent_id: str | None = None
    depth: int = 0


@dataclass
class AgentRuntime:
    agents: dict[str, AgentManifest] = field(default_factory=dict)
    tasks: dict[str, Task] = field(default_factory=dict)
    gateway: Any = None
    max_depth: int = 3
    max_steps: int = 8

    def __post_init__(self) -> None:
        if self.gateway is None:
            self.gateway = default_gateway()

    def register_agent(self, manifest: AgentManifest) -> None:
        self.agents[manifest.id] = manifest

    def create_task(self, agent_id: str, prompt: str, parent_id: str | None = None) -> Task:
        depth = 0
        if parent_id:
            parent = self.tasks[parent_id]
            depth = parent.depth + 1
            if depth > self.max_depth:
                raise ValueError("max delegation depth exceeded")
            # child cannot inherit tools parent lacked — enforced at tool eval
        task = Task(id=str(uuid.uuid4()), agent_id=agent_id, prompt=prompt, parent_id=parent_id, depth=depth)
        self.tasks[task.id] = task
        return task

    def transition(self, task_id: str, new_state: str) -> None:
        task = self.tasks[task_id]
        if new_state not in TRANSITIONS.get(task.state, set()):
            raise ValueError(f"illegal transition {task.state} -> {new_state}")
        task.state = new_state

    def plan(self, task_id: str) -> list[str]:
        task = self.tasks[task_id]
        agent = self.agents[task.agent_id]
        task.plan = [
            f"Classify request for {agent.name}",
            "Retrieve scoped knowledge",
            "Produce bounded answer",
            "Record audit",
        ]
        self.transition(task_id, "planned")
        return task.plan

    def run_step(self, task_id: str, user_approved: bool = False) -> dict[str, Any]:
        task = self.tasks[task_id]
        agent = self.agents[task.agent_id]
        if task.state == "planned":
            self.transition(task_id, "queued")
        if task.state == "queued":
            self.transition(task_id, "running")
        # Attempt knowledge search via policy
        caps = set(agent.capabilities)
        decision = self.gateway.evaluate("knowledge.search", caps, user_approved=user_approved)
        if not decision.get("allow") and decision.get("pending_approval"):
            self.transition(task_id, "awaiting_approval")
            return decision
        task.result = {
            "answer": f"[{agent.name}] Processed: {task.prompt[:200]}",
            "sources": [],
            "actions": [],
            "policy": decision,
        }
        self.transition(task_id, "completed")
        return task.result


def load_builtin_agents(runtime: AgentRuntime, directory: Path) -> None:
    for path in directory.glob("*.json"):
        runtime.register_agent(AgentManifest.from_dict(json.loads(path.read_text(encoding="utf-8"))))


if __name__ == "__main__":
    rt = AgentRuntime()
    guide = AgentManifest(
        id="atlas.guide",
        name="Atlas Guide",
        purpose="General assistant",
        tools=["knowledge.search", "notes.write"],
        capabilities=["knowledge.read", "notes.write"],
        memory_scopes=["session"],
        knowledge_scopes=["local"],
        approval_rules={},
    )
    rt.register_agent(guide)
    t = rt.create_task("atlas.guide", "What is Atlas OS?")
    print(rt.plan(t.id))
    print(rt.run_step(t.id))
