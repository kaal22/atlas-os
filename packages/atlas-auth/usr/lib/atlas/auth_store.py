#!/usr/bin/env python3
"""Atlas Auth — local accounts, sessions, roles, CSRF, login throttle."""
from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROLES = {"owner", "admin", "user", "child"}
SESSION_COOKIE = "atlas_session"
CSRF_COOKIE = "atlas_csrf"
CSRF_HEADER = "X-CSRF-Token"

# Login throttle: failures before lockout begins, then exponential backoff seconds.
_THROTTLE_WINDOW = 900  # forget counters after 15 min idle
_THROTTLE_BASE = 2
_THROTTLE_MAX = 300


def _hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000).hex()


@dataclass
class AuthStore:
    path: Path
    users: dict[str, dict[str, Any]] = field(default_factory=dict)
    sessions: dict[str, dict[str, Any]] = field(default_factory=dict)
    # throttle key -> {"fail": int, "until": int, "seen": int}
    _throttle: dict[str, dict[str, int]] = field(default_factory=dict, repr=False)

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

    @property
    def needs_bootstrap(self) -> bool:
        return len(self.users) == 0

    def create_user(self, username: str, password: str, role: str = "owner") -> None:
        if role not in ROLES:
            raise ValueError("invalid role")
        if username in self.users:
            raise ValueError("exists")
        if not username or not password:
            raise ValueError("username and password required")
        salt = secrets.token_hex(16)
        self.users[username] = {
            "role": role,
            "salt": salt,
            "password_hash": _hash(password, salt),
            "created": int(time.time()),
        }
        self.save()

    def create_owner(self, username: str, password: str) -> None:
        """Create the first owner account. Only allowed when zero users exist."""
        if not self.needs_bootstrap:
            raise PermissionError("bootstrap already completed")
        self.create_user(username, password, role="owner")

    def _throttle_key(self, kind: str, value: str) -> str:
        return f"{kind}:{value}"

    def check_throttle(self, username: str, ip: str) -> None:
        """Raise PermissionError if username or IP is throttled."""
        now = int(time.time())
        for key in (self._throttle_key("user", username), self._throttle_key("ip", ip or "unknown")):
            entry = self._throttle.get(key)
            if not entry:
                continue
            if now - entry.get("seen", 0) > _THROTTLE_WINDOW:
                self._throttle.pop(key, None)
                continue
            until = entry.get("until", 0)
            if until > now:
                raise PermissionError("too many attempts; try again later")

    def record_login_failure(self, username: str, ip: str) -> None:
        now = int(time.time())
        for key in (self._throttle_key("user", username), self._throttle_key("ip", ip or "unknown")):
            entry = self._throttle.setdefault(key, {"fail": 0, "until": 0, "seen": now})
            entry["fail"] = entry.get("fail", 0) + 1
            entry["seen"] = now
            # After 3 failures, back off: 2^(fail-2) capped
            if entry["fail"] >= 3:
                delay = min(_THROTTLE_MAX, _THROTTLE_BASE ** (entry["fail"] - 2))
                entry["until"] = now + delay

    def record_login_success(self, username: str, ip: str) -> None:
        for key in (self._throttle_key("user", username), self._throttle_key("ip", ip or "unknown")):
            self._throttle.pop(key, None)

    def login(self, username: str, password: str, ttl: int = 86400, ip: str = "") -> tuple[str, str]:
        """Authenticate and return (session_token, csrf_token)."""
        self.check_throttle(username, ip)
        user = self.users.get(username)
        if not user or _hash(password, user["salt"]) != user["password_hash"]:
            self.record_login_failure(username, ip)
            raise PermissionError("invalid credentials")
        self.record_login_success(username, ip)
        token = secrets.token_urlsafe(32)
        csrf = secrets.token_urlsafe(32)
        self.sessions[token] = {
            "username": username,
            "role": user["role"],
            "exp": int(time.time()) + ttl,
            "csrf": csrf,
        }
        self.save()
        return token, csrf

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

    def issue_csrf(self, token: str) -> str:
        sess = self.require(token)
        csrf = secrets.token_urlsafe(32)
        sess["csrf"] = csrf
        self.save()
        return csrf

    def validate_csrf(self, token: str, csrf: str | None) -> None:
        sess = self.require(token)
        expected = sess.get("csrf")
        if not expected or not csrf or not secrets.compare_digest(expected, csrf):
            raise PermissionError("csrf invalid")

    def verify_password(self, username: str, password: str) -> bool:
        """Re-auth stub helper for sensitive operations."""
        user = self.users.get(username)
        if not user:
            return False
        return _hash(password, user["salt"]) == user["password_hash"]


def session_cookie_header(token: str, max_age: int = 86400) -> str:
    return (
        f"{SESSION_COOKIE}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={max_age}"
    )


def csrf_cookie_header(csrf: str, max_age: int = 86400) -> str:
    # Readable by JS so the SPA can send X-CSRF-Token on mutating requests.
    return f"{CSRF_COOKIE}={csrf}; SameSite=Strict; Path=/; Max-Age={max_age}"


def clear_session_cookie() -> str:
    return f"{SESSION_COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"


def clear_csrf_cookie() -> str:
    return f"{CSRF_COOKIE}=; SameSite=Strict; Path=/; Max-Age=0"


def parse_cookies(header: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not header:
        return out
    for part in header.split(";"):
        part = part.strip()
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        out[k.strip()] = v.strip()
    return out


if __name__ == "__main__":
    p = Path("/tmp/atlas-auth-test.json")
    if p.exists():
        p.unlink()
    store = AuthStore(p)
    assert store.needs_bootstrap
    store.create_owner("owner", "secret")
    assert not store.needs_bootstrap
    tok, csrf = store.login("owner", "secret")
    print(store.require(tok), csrf)
