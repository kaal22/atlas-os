#!/usr/bin/env python3
"""Atlas Tool Registry — bounded local tool handlers (Phase 4)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

Handler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]


@dataclass
class ToolRegistry:
    """Maps tool_id → callable. Policy Gateway must approve before invoke."""

    handlers: dict[str, Handler] = field(default_factory=dict)
    notes_root: Path = field(default_factory=lambda: Path("/srv/atlas/notes"))
    knowledge: Any = None

    def register(self, tool_id: str, handler: Handler) -> None:
        self.handlers[tool_id] = handler

    def invoke(self, tool_id: str, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        handler = self.handlers.get(tool_id)
        if not handler:
            return {"ok": False, "error": "unregistered_handler", "tool_id": tool_id}
        try:
            return handler(args, ctx)
        except Exception as e:
            return {"ok": False, "error": str(e), "tool_id": tool_id}


def _knowledge_search(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    ks = ctx.get("knowledge")
    user = ctx.get("user_id", "local")
    query = str(args.get("query") or args.get("q") or "")
    if ks is None:
        return {"ok": True, "hits": [], "note": "knowledge_unavailable"}
    hits = ks.search(user, query)
    return {"ok": True, "hits": hits}


def _documents_read(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(args.get("path", "")))
    allowed_roots = [
        Path("/srv/atlas/documents"),
        Path("/srv/atlas/knowledge"),
        Path("/tmp/atlas-dev/documents"),
        Path("/tmp/atlas-dev/knowledge"),
    ]
    for r in ctx.get("allowed_roots") or []:
        allowed_roots.append(Path(r))
    try:
        resolved = path.resolve()
    except OSError:
        return {"ok": False, "error": "invalid_path"}
    if not any(str(resolved).startswith(str(r.resolve() if r.exists() else r)) for r in allowed_roots):
        return {"ok": False, "error": "path_outside_allowed_roots"}
    if not resolved.is_file():
        return {"ok": False, "error": "not_found"}
    text = resolved.read_text(encoding="utf-8", errors="ignore")[:20_000]
    return {"ok": True, "path": str(resolved), "text": text}


def _notes_write(args: dict[str, Any], ctx: dict[str, Any], notes_root: Path) -> dict[str, Any]:
    user = ctx.get("user_id", "local")
    name = str(args.get("name") or args.get("filename") or "note.md")
    name = Path(name).name  # no path traversal
    if not name.endswith(".md"):
        name += ".md"
    body = str(args.get("content") or args.get("text") or "")
    dest_dir = notes_root / user
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / name
    dest.write_text(body, encoding="utf-8")
    return {"ok": True, "path": str(dest), "bytes": len(body.encode("utf-8"))}


def _system_health_read(_args: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "status": "ok",
        "bind": "127.0.0.1",
        "phase": 4,
        "agent_runtime": True,
    }


def _network_fetch(_args: dict[str, Any], _ctx: dict[str, Any]) -> dict[str, Any]:
    # Even when approved, Phase 4 does not open arbitrary network — bounded stub.
    return {
        "ok": False,
        "error": "network_fetch_deferred",
        "hint": "External fetch requires trusted network mode (later phase)",
    }


def default_registry(
    notes_root: Path | None = None,
    knowledge: Any = None,
) -> ToolRegistry:
    root = notes_root or Path("/srv/atlas/notes")
    if not root.parent.exists():
        root = Path("/tmp/atlas-dev/notes")
    reg = ToolRegistry(notes_root=root, knowledge=knowledge)

    def notes_write(args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        return _notes_write(args, ctx, reg.notes_root)

    reg.register("knowledge.search", _knowledge_search)
    reg.register("documents.read", _documents_read)
    reg.register("notes.write", notes_write)
    reg.register("system.health.read", _system_health_read)
    reg.register("network.fetch", _network_fetch)
    return reg


def tool_specs_for_prompt(tool_ids: list[str]) -> str:
    """Short description of available tools for the model."""
    descriptions = {
        "knowledge.search": "Search local knowledge index. args: {query}",
        "documents.read": "Read a local document under /srv/atlas/documents. args: {path}",
        "notes.write": "Write a markdown note. args: {name, content}",
        "system.health.read": "Read local system health. args: {}",
        "network.fetch": "Fetch remote URL (requires approval). args: {url}",
    }
    lines = []
    for tid in tool_ids:
        lines.append(f"- {tid}: {descriptions.get(tid, 'registered tool')}")
    return "\n".join(lines)
