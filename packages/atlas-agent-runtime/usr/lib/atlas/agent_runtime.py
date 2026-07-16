#!/usr/bin/env python3
"""Atlas Agent Runtime — manifests, task FSM, policy-gated Ollama loop."""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pathlib import Path as _P
import sys

_HERE = _P(__file__).resolve().parent
_PACKAGES = _HERE.parents[3] if len(_HERE.parents) >= 4 else _P("/usr")
for rel in (
    _PACKAGES / "atlas-policy-gateway" / "usr" / "lib" / "atlas",
    _PACKAGES / "atlas-model-manager" / "usr" / "lib" / "atlas",
    _PACKAGES / "atlas-knowledge" / "usr" / "lib" / "atlas",
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

try:
    from model_router import chat as ollama_chat, recommend, probe_hardware
except ImportError:
    ollama_chat = None  # type: ignore
    recommend = None  # type: ignore
    probe_hardware = None  # type: ignore

from memory_store import MemoryStore  # noqa: E402
from tool_registry import default_registry, tool_specs_for_prompt  # noqa: E402

TRANSITIONS = {
    "draft": {"planned", "cancelled"},
    "planned": {"awaiting_approval", "queued", "cancelled"},
    "awaiting_approval": {"queued", "cancelled", "draft", "running"},
    "queued": {"running", "cancelled"},
    "running": {"waiting_for_user", "paused", "completed", "failed", "cancelled", "awaiting_approval"},
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
    user_id: str = "local"
    steps_taken: int = 0
    pending_approval_id: str | None = None
    pending_tool: str | None = None
    actions: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    tool_context: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgentRuntime:
    agents: dict[str, AgentManifest] = field(default_factory=dict)
    tasks: dict[str, Task] = field(default_factory=dict)
    gateway: Any = None
    tools: Any = None
    memory: MemoryStore | None = None
    knowledge: Any = None
    max_depth: int = 3
    max_steps: int = 8
    dry_run: bool = False

    def __post_init__(self) -> None:
        if self.gateway is None:
            self.gateway = default_gateway()
        if self.tools is None:
            self.tools = default_registry(knowledge=self.knowledge)
        elif self.knowledge is not None:
            self.tools.knowledge = self.knowledge
        if self.memory is None:
            mem_root = Path("/srv/atlas/memory")
            if not mem_root.parent.exists():
                mem_root = Path("/tmp/atlas-dev/memory")
            self.memory = MemoryStore(mem_root)
        if os.environ.get("ATLAS_AGENT_DRY_RUN") == "1":
            self.dry_run = True

    def register_agent(self, manifest: AgentManifest) -> None:
        self.agents[manifest.id] = manifest

    def create_task(
        self,
        agent_id: str,
        prompt: str,
        parent_id: str | None = None,
        user_id: str = "local",
    ) -> Task:
        depth = 0
        parent_caps: set[str] | None = None
        if parent_id:
            parent = self.tasks[parent_id]
            depth = parent.depth + 1
            if depth > self.max_depth:
                raise ValueError("max delegation depth exceeded")
            parent_agent = self.agents[parent.agent_id]
            parent_caps = set(parent_agent.capabilities)

        agent = self.agents[agent_id]
        caps = set(agent.capabilities)
        # Child cannot inherit tools/caps the parent lacked
        if parent_caps is not None and not caps.issubset(parent_caps):
            raise PermissionError("child_agent_capability_escalation")

        task = Task(
            id=str(uuid.uuid4()),
            agent_id=agent_id,
            prompt=prompt,
            parent_id=parent_id,
            depth=depth,
            user_id=user_id,
        )
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
            "Retrieve scoped knowledge (policy-gated)",
            "Produce bounded local answer",
            "Record memory + audit",
        ]
        self.transition(task_id, "planned")
        return task.plan

    def approve(self, task_id: str, approval_id: str, approved: bool = True) -> dict[str, Any]:
        task = self.tasks[task_id]
        if task.state != "awaiting_approval":
            raise ValueError("task_not_awaiting_approval")
        if task.pending_approval_id != approval_id:
            raise ValueError("approval_mismatch")
        pending = self.gateway.pending_approvals.pop(approval_id, None)
        if not approved:
            self.transition(task_id, "cancelled")
            task.result = {"error": "approval_denied", "approval_id": approval_id}
            return task.result
        # Resume with user_approved
        task.pending_approval_id = None
        tool_id = task.pending_tool or (pending or {}).get("tool_id")
        self.transition(task_id, "queued")
        return self.run_step(task_id, user_approved=True, force_tool=tool_id)

    def _run_tool(
        self,
        task: Task,
        agent: AgentManifest,
        tool_id: str,
        args: dict[str, Any],
        user_approved: bool,
    ) -> dict[str, Any]:
        if tool_id not in agent.tools:
            return {"allow": False, "reason": "tool_not_on_manifest", "tool_id": tool_id}

        caps = set(agent.capabilities)
        # Parent capability inheritance check for delegated tasks
        if task.parent_id:
            parent = self.tasks[task.parent_id]
            parent_caps = set(self.agents[parent.agent_id].capabilities)
            if not caps.issubset(parent_caps):
                return {"allow": False, "reason": "parent_capability_violation"}

        decision = self.gateway.evaluate(tool_id, caps, user_approved=user_approved)
        if not decision.get("allow"):
            if decision.get("pending_approval"):
                task.pending_approval_id = decision["pending_approval"]
                task.pending_tool = tool_id
            return decision

        ctx = {
            "user_id": task.user_id,
            "agent_id": agent.id,
            "task_id": task.id,
            "knowledge": self.knowledge or getattr(self.tools, "knowledge", None),
            "token": decision.get("token"),
        }

        result = self.tools.invoke(tool_id, args, ctx)
        action = {"tool": tool_id, "args": args, "result": result, "policy": decision}
        task.actions.append(action)
        if tool_id == "knowledge.search" and result.get("hits"):
            task.sources.extend(result["hits"])
        task.tool_context.append({"tool": tool_id, "result": result})
        return {"allow": True, "tool_result": result, "policy": decision}

    def run_step(
        self,
        task_id: str,
        user_approved: bool = False,
        force_tool: str | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        task = self.tasks[task_id]
        agent = self.agents[task.agent_id]

        if task.state == "planned":
            self.transition(task_id, "queued")
        if task.state == "queued":
            self.transition(task_id, "running")
        if task.state == "awaiting_approval" and user_approved:
            self.transition(task_id, "running")

        if task.state not in {"running"}:
            return task.result or {"error": f"cannot_run_in_state_{task.state}"}

        task.steps_taken += 1
        if task.steps_taken > self.max_steps:
            self.transition(task_id, "failed")
            task.result = {"error": "max_steps_exceeded"}
            return task.result

        # Optional forced tool (post-approval) or automatic knowledge search for Guide/Research
        tools_to_try: list[tuple[str, dict[str, Any]]] = []
        if force_tool:
            tools_to_try.append((force_tool, {"query": task.prompt, "url": task.prompt.strip().split()[0] if task.prompt else ""}))
        elif "network.fetch" in agent.tools and task.prompt.strip().lower().startswith("http"):
            url = task.prompt.strip().split()[0]
            tools_to_try.append(("network.fetch", {"url": url}))
        elif "knowledge.search" in agent.tools and not task.tool_context:
            tools_to_try.append(("knowledge.search", {"query": task.prompt}))
        elif "system.health.read" in agent.tools and agent.id == "atlas.system-steward":
            tools_to_try.append(("system.health.read", {}))

        for tool_id, args in tools_to_try:
            decision = self._run_tool(task, agent, tool_id, args, user_approved=user_approved)
            if not decision.get("allow") and decision.get("pending_approval"):
                self.transition(task_id, "awaiting_approval")
                task.result = {
                    "pending_approval": decision["pending_approval"],
                    "mode": decision.get("mode"),
                    "tool_id": tool_id,
                    "answer": None,
                    "sources": task.sources,
                    "actions": task.actions,
                }
                return task.result
            if not decision.get("allow"):
                # Non-pending deny: continue without that tool (bounded)
                task.actions.append({"tool": tool_id, "denied": decision})

        # Build LLM messages
        tool_bits = ""
        if task.tool_context:
            tool_bits = "Tool results:\n" + json.dumps(task.tool_context, indent=2)[:4000]

        system = (
            f"You are {agent.name}, an Atlas OS local assistant. "
            f"Purpose: {agent.purpose}. "
            "Stay offline-first. Do not claim to have network or root access. "
            "Be concise and helpful.\n"
            f"Available tools (already gated by policy):\n{tool_specs_for_prompt(agent.tools)}"
        )
        messages = [
            {"role": "system", "content": system},
        ]
        if history:
            for turn in history[-12:]:
                role = turn.get("role", "")
                content = (turn.get("content") or "").strip()
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content[:4000]})
        messages.append({"role": "user", "content": task.prompt})
        if tool_bits:
            messages.append({"role": "assistant", "content": tool_bits})

        profile = agent.model_profile
        if probe_hardware and recommend:
            hw = probe_hardware()
            # Force CPU-safe if profile needs VRAM the machine lacks
            from model_router import is_compatible  # local import

            if not is_compatible(profile, hw):
                profile = recommend(hw)

        answer: str
        model_meta: dict[str, Any] = {}
        if self.dry_run or ollama_chat is None:
            answer = (
                f"[{agent.name} dry-run] Processed locally: {task.prompt[:200]}"
            )
            model_meta = {"model": "dry-run", "profile": profile}
        else:
            try:
                out = ollama_chat(messages, profile=profile)
                answer = out["content"] or f"[{agent.name}] (empty model response)"
                model_meta = {"model": out.get("model"), "profile": out.get("profile")}
            except Exception as e:
                self.transition(task_id, "failed")
                task.result = {
                    "error": "ollama_unavailable",
                    "detail": str(e),
                    "hint": "Ensure Ollama is running and a CPU model (e.g. qwen3:4b) is loaded",
                    "sources": task.sources,
                    "actions": task.actions,
                }
                return task.result

        # Session memory
        if self.memory and "session" in agent.memory_scopes:
            try:
                self.memory.append(
                    "session",
                    f"{task.user_id}:{task.id[:8]}",
                    {"prompt": task.prompt[:500], "answer": answer[:1000], "agent": agent.id},
                )
            except Exception:
                pass

        task.result = {
            "answer": answer,
            "sources": task.sources,
            "actions": task.actions,
            "model": model_meta,
            "agent": agent.id,
        }
        self.transition(task_id, "completed")
        return task.result


def load_builtin_agents(runtime: AgentRuntime, directory: Path) -> None:
    for path in directory.glob("*.json"):
        runtime.register_agent(AgentManifest.from_dict(json.loads(path.read_text(encoding="utf-8"))))


if __name__ == "__main__":
    os.environ["ATLAS_AGENT_DRY_RUN"] = "1"
    rt = AgentRuntime(dry_run=True)
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
