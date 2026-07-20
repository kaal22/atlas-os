#!/usr/bin/env python3
"""Local chat thread storage for Atlas Command Centre."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

MAX_THREADS = 60
MAX_MESSAGES = 100


def _safe_user(user: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in user)[:64]


def _safe_id(thread_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in thread_id)[:64]


def _preview(messages: list[dict[str, Any]]) -> str:
    for msg in messages:
        if msg.get("role") == "user":
            text = (msg.get("content") or "").strip()
            if text:
                return text[:80]
    return ""


def _sanitize_messages(messages: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in messages or []:
        if not isinstance(raw, dict):
            continue
        role = raw.get("role")
        content = raw.get("content")
        if role not in {"user", "assistant"}:
            continue
        if not isinstance(content, str):
            content = str(content or "")
        item: dict[str, Any] = {"role": role, "content": content[:8000]}
        if role == "assistant" and raw.get("sources"):
            sources = []
            for src in raw.get("sources") or []:
                if not isinstance(src, dict):
                    continue
                sources.append(
                    {
                        "doc_id": src.get("doc_id"),
                        "name": src.get("name"),
                        "path": src.get("path"),
                        "chunk_index": src.get("chunk_index"),
                    }
                )
            if sources:
                item["sources"] = sources[:8]
        if raw.get("isErr"):
            item["isErr"] = True
        out.append(item)
    return out


class ChatStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _user_dir(self, user: str) -> Path:
        d = self.root / _safe_user(user)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def list_threads(self, user: str) -> list[dict[str, Any]]:
        threads: list[dict[str, Any]] = []
        for path in self._user_dir(user).glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            threads.append(
                {
                    "id": data.get("id", path.stem),
                    "title": data.get("title") or "New chat",
                    "agent": data.get("agent", "atlas.guide"),
                    "updated_at": int(data.get("updated_at") or 0),
                    "created_at": int(data.get("created_at") or 0),
                    "preview": _preview(data.get("messages") or []),
                }
            )
        threads.sort(key=lambda t: t.get("updated_at", 0), reverse=True)
        return threads[:MAX_THREADS]

    def get_thread(self, user: str, thread_id: str) -> dict[str, Any] | None:
        path = self._user_dir(user) / f"{_safe_id(thread_id)}.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def create_thread(self, user: str, agent: str = "atlas.guide") -> dict[str, Any]:
        self._prune_old(user)
        now = int(time.time())
        thread = {
            "id": uuid.uuid4().hex[:12],
            "title": "New chat",
            "agent": agent,
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        self._write(user, thread)
        return thread

    def save_thread(
        self,
        user: str,
        thread_id: str,
        messages: list[Any] | None = None,
        agent: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any] | None:
        thread = self.get_thread(user, thread_id)
        if not thread:
            return None
        if messages is not None:
            thread["messages"] = _sanitize_messages(messages)[-MAX_MESSAGES:]
        thread["updated_at"] = int(time.time())
        if agent:
            thread["agent"] = agent
        if title:
            thread["title"] = title[:120]
        elif messages is not None and thread.get("title") == "New chat":
            for msg in thread["messages"]:
                if msg.get("role") == "user" and (msg.get("content") or "").strip():
                    text = msg["content"].strip()
                    thread["title"] = text[:60] + ("…" if len(text) > 60 else "")
                    break
        self._write(user, thread)
        return thread

    def delete_thread(self, user: str, thread_id: str) -> bool:
        path = self._user_dir(user) / f"{_safe_id(thread_id)}.json"
        if path.is_file():
            path.unlink()
            return True
        return False

    def _write(self, user: str, thread: dict[str, Any]) -> None:
        path = self._user_dir(user) / f"{_safe_id(str(thread['id']))}.json"
        path.write_text(json.dumps(thread, indent=2), encoding="utf-8")

    def _prune_old(self, user: str) -> None:
        threads = self.list_threads(user)
        if len(threads) < MAX_THREADS:
            return
        for item in threads[MAX_THREADS - 1 :]:
            self.delete_thread(user, str(item["id"]))
