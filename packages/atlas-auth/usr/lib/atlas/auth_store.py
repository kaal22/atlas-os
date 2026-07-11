#!/usr/bin/env python3
"""Atlas Auth — local accounts, sessions, roles."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROLES = {"owner", "admin", "user", "child"}


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()


@dataclass
class AuthStore:
    path: Path
    users: dict[str, dict[str, Any]] = field(default_factory=dict)
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)

    def load(self) -> None:
        if self.path.exists():
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.users = data.get("users", {})
            self.sessions = data.get("sessions", {})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"users": self.users, "sessions": self.sessions}, indent=2),
            encoding="utf-8",
        )

    def create_user(self, username: str, password: str, role: str = "owner") -> None:
        if role not in ROLES:
            raise ValueError("invalid role")
        if username in self.users:
            raise ValueError("exists")
        salt = secrets.token_hex(16)
        self.users[username] = {
            "role": role,
            "salt": salt,
            "password_hash": _hash(password, salt),
            "created": int(time.time()),
        }
        self.save()

    def login(self, username: str, password: str, ttl: int = 86400) -> str:
        user = self.users.get(username)
        if not user:
            raise PermissionError("invalid credentials")
        if _hash(password, user["salt"]) != user["password_hash"]:
            raise PermissionError("invalid credentials")
        token = secrets.token_urlsafe(32)
        self.sessions[token] = {
            "username": username,
            "role": user["role"],
            "exp": int(time.time()) + ttl,
        }
        self.save()
        return token

    def require(self, token: str, roles: set[str] | None = None) -> dict[str, Any]:
        sess = self.sessions.get(token)
        if not sess or sess["exp"] < time.time():
            raise PermissionError("session expired")
        if roles and sess["role"] not in roles:
            raise PermissionError("forbidden")
        return sess

    def logout(self, token: str) -> None:
        self.sessions.pop(token, None)
        self.save()


if __name__ == "__main__":
    p = Path("/tmp/atlas-auth-test.json")
    if p.exists():
        p.unlink()
    store = AuthStore(p)
    store.create_user("atlas", "change-me", "owner")
    tok = store.login("atlas", "change-me")
    print(store.require(tok))
