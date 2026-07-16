#!/usr/bin/env python3
"""Atlas agent memory scopes — simple JSON files per scope/session."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

KNOWN_SCOPES = {
    "session",
    "user_preferences",
    "research_projects",
}


class MemoryStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, scope: str, key: str) -> Path:
        if scope not in KNOWN_SCOPES:
            raise ValueError(f"unknown memory scope: {scope}")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in key)[:64]
        d = self.root / scope
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{safe}.json"

    def get(self, scope: str, key: str) -> dict[str, Any]:
        path = self._path(scope, key)
        if not path.exists():
            return {"scope": scope, "key": key, "entries": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def append(self, scope: str, key: str, entry: dict[str, Any]) -> dict[str, Any]:
        data = self.get(scope, key)
        item = {**entry, "ts": int(time.time())}
        data.setdefault("entries", []).append(item)
        # Cap session history
        if scope == "session" and len(data["entries"]) > 40:
            data["entries"] = data["entries"][-40:]
        path = self._path(scope, key)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return data
