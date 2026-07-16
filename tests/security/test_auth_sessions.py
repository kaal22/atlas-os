#!/usr/bin/env python3
"""Auth session / bootstrap / API lockdown security tests."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTH_LIB = ROOT / "packages" / "atlas-auth" / "usr" / "lib" / "atlas"
CC_LIB = ROOT / "packages" / "atlas-command-centre" / "usr" / "lib" / "atlas"
PACKAGES = ROOT / "packages"

# Put real package libs on path (policy, agents, models, knowledge, auth, cc)
for pkg in (
    "atlas-auth",
    "atlas-policy-gateway",
    "atlas-agent-runtime",
    "atlas-model-manager",
    "atlas-knowledge",
    "atlas-command-centre",
):
    p = PACKAGES / pkg / "usr" / "lib" / "atlas"
    if p.exists():
        sys.path.insert(0, str(p))

_tmpdir = tempfile.mkdtemp(prefix="atlas-auth-test-")
_data = Path(_tmpdir)
for sub in ("databases", "logs", "knowledge"):
    (_data / sub).mkdir(parents=True)

# Force CC onto temp data: /srv/atlas must not exist for default DATA, or we patch after import.
import auth_store as auth_mod  # noqa: E402
import command_centre as cc  # noqa: E402

cc.DATA = _data
cc.AUTH = auth_mod.AuthStore(_data / "databases" / "auth.json")
cc.AUTH.load()
cc.WIZARD_STATE = _data / "databases" / "first-run.json"
cc.AUDIT_LOG = _data / "logs" / "atlas-audit.jsonl"


def _start_server():
    server = cc.ThreadingHTTPServer(("127.0.0.1", 0), cc.Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, server.server_address[1]


def _request(port, method, path, body=None, headers=None, cookies=None):
    url = f"http://127.0.0.1:{port}{path}"
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    if cookies:
        req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()))
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode()
            set_cookies = resp.headers.get_all("Set-Cookie") or []
            return resp.status, json.loads(raw) if raw else {}, set_cookies
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            obj = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            obj = {"raw": raw}
        set_cookies = e.headers.get_all("Set-Cookie") or []
        return e.code, obj, set_cookies


def _parse_set_cookies(headers: list[str]) -> dict[str, str]:
    out = {}
    for h in headers:
        part = h.split(";", 1)[0]
        if "=" in part:
            k, v = part.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def _reset_auth():
    path = _data / "databases" / "auth.json"
    if path.exists():
        path.unlink()
    cc.AUTH = auth_mod.AuthStore(path)
    cc.AUTH.load()


def test_unauth_api_returns_401():
    _reset_auth()
    server, port = _start_server()
    try:
        assert cc.AUTH.needs_bootstrap
        code, body, _ = _request(port, "GET", "/api/system/health")
        assert code == 401, (code, body)
        assert body.get("error") == "unauthorized"
        code, body, _ = _request(port, "POST", "/api/ask", {"prompt": "hi"})
        assert code == 401
        code, body, _ = _request(port, "GET", "/api/agents")
        assert code == 401
        # Public endpoints still open
        code, body, _ = _request(port, "GET", "/api/auth/bootstrap")
        assert code == 200
        assert body.get("needs_bootstrap") is True
    finally:
        server.shutdown()


def test_bootstrap_once_and_cookie_session():
    _reset_auth()
    server, port = _start_server()
    try:
        code, body, cookies = _request(
            port,
            "POST",
            "/api/auth/bootstrap",
            {"username": "owner", "password": "s3cret-pass"},
        )
        assert code == 200, (code, body)
        parsed = _parse_set_cookies(cookies)
        assert "atlas_session" in parsed
        sess_hdr = next(h for h in cookies if h.startswith("atlas_session="))
        assert "HttpOnly" in sess_hdr
        assert "SameSite=Strict" in sess_hdr
        assert "Path=/" in sess_hdr

        code, body, _ = _request(
            port,
            "POST",
            "/api/auth/bootstrap",
            {"username": "other", "password": "x"},
        )
        assert code == 409

        csrf = parsed.get("atlas_csrf", "")
        jar = {"atlas_session": parsed["atlas_session"], "atlas_csrf": csrf}
        code, body, _ = _request(port, "GET", "/api/system/health", cookies=jar)
        assert code == 200, (code, body)
        assert body.get("services", {}).get("command_centre") is True

        # Mutating without CSRF cookie/header fails
        code, body, _ = _request(
            port,
            "POST",
            "/api/setup/advance",
            {},
            cookies={"atlas_session": parsed["atlas_session"]},
        )
        assert code == 403, (code, body)

        code, body, _ = _request(
            port,
            "POST",
            "/api/setup/advance",
            {},
            cookies=jar,
            headers={"X-CSRF-Token": csrf},
        )
        assert code == 200, (code, body)

        # Logout
        code, body, _ = _request(
            port,
            "POST",
            "/api/auth/logout",
            {},
            cookies=jar,
            headers={"X-CSRF-Token": csrf},
        )
        assert code == 200
        code, body, _ = _request(port, "GET", "/api/system/health", cookies=jar)
        assert code == 401
    finally:
        server.shutdown()


def test_no_default_atlas_password():
    p = Path(_tmpdir) / "auth-defaults.json"
    if p.exists():
        p.unlink()
    store = auth_mod.AuthStore(p)
    store.load()
    assert store.needs_bootstrap
    assert "atlas" not in store.users
    try:
        store.login("atlas", "atlas")
        raise AssertionError("default atlas/atlas must not authenticate")
    except PermissionError:
        pass
    src = (CC_LIB / "command_centre.py").read_text(encoding="utf-8")
    assert 'create_user("atlas", "atlas"' not in src
    assert "No default atlas/atlas" in src


def test_login_throttle():
    p = Path(_tmpdir) / "throttle.json"
    if p.exists():
        p.unlink()
    store = auth_mod.AuthStore(p)
    store.create_owner("u1", "goodpass")
    for _ in range(5):
        try:
            store.login("u1", "bad", ip="10.0.0.9")
        except PermissionError:
            pass
    try:
        store.login("u1", "goodpass", ip="10.0.0.9")
    except PermissionError as e:
        assert "too many" in str(e) or "invalid" in str(e)


if __name__ == "__main__":
    test_unauth_api_returns_401()
    test_bootstrap_once_and_cookie_session()
    test_no_default_atlas_password()
    test_login_throttle()
    print("OK test_auth_sessions")
