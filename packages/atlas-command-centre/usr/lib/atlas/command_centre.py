#!/usr/bin/env python3
"""Atlas Command Centre — local API + UI on 127.0.0.1:8787."""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import request as urlrequest
from urllib.error import URLError
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
# Source tree: .../packages/<pkg>/usr/lib/atlas → packages dir is parents[3]
PACKAGES = HERE.parents[3] if len(HERE.parents) >= 4 else Path("/usr")
LIB_CANDIDATES = [
    HERE,
    PACKAGES / "atlas-auth" / "usr" / "lib" / "atlas",
    PACKAGES / "atlas-policy-gateway" / "usr" / "lib" / "atlas",
    PACKAGES / "atlas-agent-runtime" / "usr" / "lib" / "atlas",
    PACKAGES / "atlas-model-manager" / "usr" / "lib" / "atlas",
    PACKAGES / "atlas-knowledge" / "usr" / "lib" / "atlas",
    PACKAGES / "atlas-content-manager" / "usr" / "lib" / "atlas",
    PACKAGES / "atlas-backup" / "usr" / "lib" / "atlas",
    PACKAGES / "atlas-updater" / "usr" / "lib" / "atlas",
    PACKAGES / "atlas-system-daemon" / "usr" / "lib" / "atlas",
    Path("/usr/lib/atlas"),
]
for c in LIB_CANDIDATES:
    if c.exists():
        sys.path.insert(0, str(c))

from auth_store import (  # noqa: E402
    CSRF_COOKIE,
    CSRF_HEADER,
    SESSION_COOKIE,
    AuthStore,
    clear_csrf_cookie,
    clear_session_cookie,
    csrf_cookie_header,
    parse_cookies,
    session_cookie_header,
)
from policy_gateway import default_gateway  # noqa: E402
from agent_runtime import AgentRuntime, AgentManifest  # noqa: E402
from model_router import probe_hardware, recommend, recommendation_bundle  # noqa: E402
from model_catalog import model_setup_status, start_pull, get_job  # noqa: E402
from knowledge_service import KnowledgeService, SUPPORTED_EXTENSIONS  # noqa: E402
from content_manager import (  # noqa: E402
    PackError,
    check_compatibility,
    find_packs_on_paths,
    install_pack,
    list_usb_pack_dirs,
    load_catalogue,
    load_installed,
    merge_catalogue_status,
    read_pack_metadata,
    uninstall_pack,
)
from backup_service import (  # noqa: E402
    BackupError,
    create_backup,
    list_backups,
    restore_backup,
    verify_backup,
)
from updater import (  # noqa: E402
    find_update_bundles,
    read_bundle_metadata,
)
from chat_store import ChatStore  # noqa: E402

try:
    from gpu_detect import as_api_dict as gpu_as_api_dict
except ImportError:
    gpu_as_api_dict = None  # type: ignore

HOST = "127.0.0.1"
PORT = 8787
DATA = Path("/srv/atlas") if Path("/srv/atlas").exists() else Path("/tmp/atlas-dev")
AUTH = AuthStore(DATA / "databases" / "auth.json")
AUTH.load()
# No default atlas/atlas account — bootstrap creates the first owner.

GW = default_gateway()
KS = KnowledgeService(DATA / "knowledge")
RT = AgentRuntime(gateway=GW, knowledge=KS)
CHAT = ChatStore(DATA / "chat")

CATALOGUE_PATHS = [
    Path("/usr/share/atlas/catalogue.json"),
    PACKAGES / "atlas-content-manager" / "usr" / "share" / "atlas" / "catalogue.json",
    Path(__file__).resolve().parents[3] / "content" / "catalogues" / "catalogue.json",
]
PACK_INCOMING = DATA / "content-packs" / "incoming"
PACK_BUNDLED = Path("/usr/share/atlas/packs")
BACKUP_DIR = DATA / "backups" / "full"
UPDATE_INCOMING = DATA / "updates" / "incoming"
UPDATE_BUNDLED = Path("/usr/share/atlas/updates")


def _catalogue_file() -> Path:
    for p in CATALOGUE_PATHS:
        if p.is_file():
            return p
    return CATALOGUE_PATHS[0]


def _pack_browse_roots() -> list[Path]:
    roots = [PACK_INCOMING, PACK_BUNDLED, DATA / "content-packs"]
    roots.extend(Path(p) for p in list_usb_pack_dirs())
    out: list[Path] = []
    seen: set[str] = set()
    for r in roots:
        try:
            key = str(r.resolve()) if r.exists() else str(r)
        except OSError:
            key = str(r)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _pack_path_allowed(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    if not str(path).endswith(".atlas-pack"):
        return False
    allowed = [Path("/media"), Path("/run/media"), Path("/mnt"), DATA, Path("/usr/share/atlas/packs")]
    for root in allowed:
        try:
            rr = root.resolve() if root.exists() else root
        except OSError:
            rr = root
        if str(resolved).startswith(str(rr)):
            return True
    return False


def _update_path_allowed(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    if not str(path).endswith(".atlas-update"):
        return False
    allowed = [
        Path("/media"), Path("/run/media"), Path("/mnt"),
        DATA, UPDATE_INCOMING, UPDATE_BUNDLED, Path("/usr/share/atlas/updates"),
    ]
    for root in allowed:
        try:
            rr = root.resolve() if root.exists() else root
        except OSError:
            rr = root
        if str(resolved).startswith(str(rr)):
            return True
    return False


def _backup_path_allowed(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    if not str(path).endswith(".atlasbak"):
        return False
    roots = [BACKUP_DIR, DATA / "backups"]
    for root in roots:
        try:
            rr = root.resolve() if root.exists() else root
        except OSError:
            rr = root
        if str(resolved).startswith(str(rr)):
            return True
    return False


def _resolve_catalogue_pack(catalogue_id: str) -> Path | None:
    cat = load_catalogue(_catalogue_file())
    entry = next((p for p in cat.get("packs") or [] if p.get("id") == catalogue_id), None)
    if entry and entry.get("bundle_file"):
        candidate = PACK_BUNDLED / str(entry["bundle_file"])
        if candidate.is_file():
            return candidate
    if PACK_BUNDLED.is_dir():
        for f in PACK_BUNDLED.glob("*.atlas-pack"):
            try:
                meta = read_pack_metadata(f)
                if meta["manifest"].get("id") == catalogue_id:
                    return f
            except PackError:
                continue
    return None

for agent_file in [
    Path("/usr/share/atlas/agents"),
    HERE.parents[1] / "share" / "atlas" / "agents",
    PACKAGES / "atlas-agent-runtime" / "usr" / "share" / "atlas" / "agents",
]:
    if agent_file.exists():
        for p in agent_file.glob("*.json"):
            RT.register_agent(AgentManifest.from_dict(json.loads(p.read_text(encoding="utf-8"))))
        break

WIZARD_STATE = DATA / "databases" / "first-run.json"
AUDIT_LOG = Path(os.environ.get("ATLAS_AUDIT_LOG", str(DATA / "logs" / "atlas-audit.jsonl")))

# Public API paths (no session required)
PUBLIC_GET = {"/api/auth/bootstrap"}
PUBLIC_POST = {"/api/auth/login", "/api/auth/bootstrap"}


def audit_event(event: dict[str, Any]) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    payload = {**event, "ts": datetime.now(timezone.utc).isoformat(), "source": "command_centre"}
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


INGEST_EXTENSIONS = set(SUPPORTED_EXTENSIONS)


def _knowledge_roots(username: str) -> list[tuple[str, Path]]:
    """Labelled browse roots for the signed-in user."""
    out: list[tuple[str, Path]] = []
    seen: set[str] = set()
    candidates: list[tuple[str, Path]] = [
        ("Atlas documents", DATA / "documents"),
        ("Atlas documents", Path("/srv/atlas/documents")),
        ("Dev documents", Path("/tmp/atlas-dev/documents")),
    ]
    home = Path("/home") / username
    for sub, label in (
        ("Documents", "My Documents"),
        ("documents", "My documents"),
        ("Desktop", "My Desktop"),
    ):
        candidates.append((label, home / sub))
    for label, p in candidates:
        try:
            key = str(p.resolve()) if p.exists() else str(p)
        except OSError:
            key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.exists() or p == DATA / "documents":
            if p == DATA / "documents":
                p.mkdir(parents=True, exist_ok=True)
            out.append((label, p))
    return out


def _path_allowed(path: Path, username: str) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for _, root in _knowledge_roots(username):
        try:
            root_r = root.resolve()
        except OSError:
            root_r = root
        if str(resolved).startswith(str(root_r)):
            return True
    return False


def browse_knowledge(path_str: str, username: str) -> dict[str, Any]:
    if not path_str:
        entries = []
        for label, root in _knowledge_roots(username):
            entries.append({
                "name": label,
                "path": str(root),
                "kind": "dir",
                "size": 0,
            })
        return {"cwd": "", "parent": None, "entries": entries, "roots": True}

    cwd = Path(path_str)
    if not _path_allowed(cwd, username):
        raise PermissionError("path_not_allowed")
    if not cwd.exists():
        raise FileNotFoundError(path_str)
    if not cwd.is_dir():
        raise NotADirectoryError(path_str)

    entries: list[dict[str, Any]] = []
    try:
        children = sorted(cwd.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as e:
        raise PermissionError(str(e)) from e

    for child in children:
        if child.name.startswith("."):
            continue
        if child.is_dir():
            entries.append({"name": child.name, "path": str(child), "kind": "dir", "size": 0})
        elif child.is_file() and child.suffix.lower() in INGEST_EXTENSIONS:
            try:
                size = child.stat().st_size
            except OSError:
                size = 0
            entries.append({"name": child.name, "path": str(child), "kind": "file", "size": size})

    parent: str | None = None
    cwd_resolved = cwd.resolve()
    for _, root in _knowledge_roots(username):
        try:
            root_r = root.resolve()
        except OSError:
            continue
        if str(cwd_resolved) == str(root_r):
            parent = ""
            break
        if str(cwd_resolved).startswith(str(root_r) + "/"):
            parent = str(cwd.parent)
            break

    return {"cwd": str(cwd), "parent": parent, "entries": entries, "roots": False}


def knowledge_library(username: str) -> dict[str, Any]:
    docs = KS.library(username)
    st = KS.status()
    return {"documents": docs, "count": len(docs), "knowledge": st}


SERVICE_SPECS = [
    ("kiwix", "http://127.0.0.1:8080/"),
    ("qdrant", "http://127.0.0.1:6333/readyz"),
    ("nomad", "http://127.0.0.1:8090/api/health"),
    ("ollama", "http://127.0.0.1:11434/api/tags"),
]


def _probe_one(name: str, url: str) -> dict[str, Any]:
    ok = False
    http = 0
    try:
        req = urlrequest.Request(url, method="GET")
        with urlrequest.urlopen(req, timeout=1.5) as resp:
            http = int(getattr(resp, "status", 200))
            ok = True
    except (URLError, OSError, ValueError):
        pass
    except Exception:
        pass
    return {"name": name, "url": url, "ok": ok, "http": http}


def probe_services() -> dict[str, Any]:
    """Loopback HTTP probes — parallel, no subprocess (CC security boundary)."""
    services: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=min(8, len(SERVICE_SPECS) or 1)) as pool:
        futures = [pool.submit(_probe_one, name, url) for name, url in SERVICE_SPECS]
        for fut in as_completed(futures):
            try:
                services.append(fut.result())
            except Exception:
                pass
    order = {name: i for i, (name, _) in enumerate(SERVICE_SPECS)}
    services.sort(key=lambda s: order.get(s["name"], 99))
    return {"services": services}


UI_PATH = HERE / "command_centre_ui.html"
UI = UI_PATH.read_text(encoding="utf-8")
LOGO_PATH = HERE / "atlas-logo.png"


class Handler(BaseHTTPRequestHandler):
    def _client_ip(self) -> str:
        return self.client_address[0] if self.client_address else ""

    def _json(self, code: int, obj, extra_headers: list[tuple[str, str]] | None = None) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for k, v in extra_headers:
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _session_token(self) -> str | None:
        cookies = parse_cookies(self.headers.get("Cookie"))
        tok = cookies.get(SESSION_COOKIE)
        if tok:
            return tok
        # Legacy Bearer accepted only as secondary for migrations / tooling — not primary.
        hdr = self.headers.get("Authorization", "")
        if hdr.startswith("Bearer "):
            return hdr[7:].strip() or None
        return None

    def _auth(self):
        tok = self._session_token()
        if not tok:
            return None
        try:
            return AUTH.require(tok)
        except PermissionError:
            return None

    def _require_auth(self, path: str, method: str):
        """Return session dict or send 401 and return None."""
        if method == "GET" and path in PUBLIC_GET:
            return True
        if method == "POST" and path in PUBLIC_POST:
            return True
        sess = self._auth()
        if sess is None:
            self._json(401, {"error": "unauthorized"})
            return None
        return sess

    def _require_csrf(self, sess) -> bool:
        tok = self._session_token()
        csrf = self.headers.get(CSRF_HEADER) or parse_cookies(self.headers.get("Cookie")).get(CSRF_COOKIE)
        try:
            AUTH.validate_csrf(tok or "", csrf)
            return True
        except PermissionError:
            self._json(403, {"error": "csrf_invalid"})
            return False

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            body = UI.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/assets/atlas-logo.png":
            if not LOGO_PATH.is_file():
                return self._json(404, {"error": "not_found"})
            body = LOGO_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.end_headers()
            self.wfile.write(body)
            return

        if not path.startswith("/api/"):
            return self._json(404, {"error": "not_found"})

        if path == "/api/auth/bootstrap":
            return self._json(200, {"needs_bootstrap": AUTH.needs_bootstrap})

        sess = self._require_auth(path, "GET")
        if sess is None:
            return
        if sess is True:
            return

        if path == "/api/auth/session":
            return self._json(200, {"username": sess["username"], "role": sess["role"]})

        if path == "/api/system/health":
            health = {"status": "ok", "bind": f"{HOST}:{PORT}", "services": {"command_centre": True}}
            try:
                bundle = recommendation_bundle()
                if bundle.get("warning"):
                    # Advisory only — CPU-first installs stay healthy without a GPU.
                    health["gpu_warning"] = bundle["warning"]
            except Exception:
                pass
            try:
                ms = model_setup_status()
                health["ollama"] = ms.get("ollama_reachable")
                health["models_ready"] = ms.get("ready")
                health["embed_ready"] = ms.get("embed_ready")
                health["model_profile"] = ms.get("profile")
                if not ms.get("ollama_reachable"):
                    health["status"] = "degraded"
                    health["hint"] = "Ollama is not running — AI chat needs it."
                elif not ms.get("ready"):
                    health["status"] = "degraded"
                    health["hint"] = "Download a model in Command Centre → Models"
            except Exception:
                pass
            try:
                health["knowledge"] = KS.status()
            except Exception:
                pass
            try:
                health["content"] = {"installed": len(load_installed(DATA).get("packs", []))}
            except Exception:
                pass
            try:
                from updater import get_installed_version
                health["version"] = get_installed_version().get("version")
            except Exception:
                pass
            return self._json(200, health)
        if path == "/api/system/services":
            try:
                return self._json(200, probe_services())
            except Exception as e:
                return self._json(200, {"services": [], "error": str(e)})
        if path == "/api/agents":
            agents = []
            for a in RT.agents.values():
                agents.append({
                    "id": a.id,
                    "name": a.name,
                    "purpose": a.purpose,
                    "tools": a.tools,
                    "model_profile": a.model_profile,
                    "version": a.version,
                })
            return self._json(200, {"agents": agents})
        if path == "/api/knowledge/browse":
            qs = parse_qs(urlparse(self.path).query)
            browse_path = (qs.get("path") or [""])[0]
            try:
                return self._json(200, browse_knowledge(browse_path, sess["username"]))
            except PermissionError as e:
                return self._json(403, {"error": str(e)})
            except FileNotFoundError:
                return self._json(404, {"error": "folder_not_found"})
            except NotADirectoryError:
                return self._json(400, {"error": "not_a_directory"})
        if path == "/api/knowledge/library":
            return self._json(200, knowledge_library(sess["username"]))
        if path == "/api/knowledge/status":
            try:
                return self._json(200, KS.status())
            except Exception as e:
                return self._json(500, {"error": str(e)})
        if path == "/api/knowledge/chunk":
            qs = parse_qs(urlparse(self.path).query)
            doc_id = (qs.get("doc_id") or [""])[0]
            try:
                chunk_index = int((qs.get("chunk_index") or ["0"])[0])
            except ValueError:
                chunk_index = 0
            chunk = KS.get_chunk(sess["username"], doc_id, chunk_index)
            if not chunk:
                return self._json(404, {"error": "chunk_not_found"})
            return self._json(200, chunk)
        if path == "/api/approvals":
            pending = []
            for aid, meta in GW.pending_approvals.items():
                pending.append({"approval_id": aid, **meta})
            # Attach task ids when known
            by_approval = {
                t.pending_approval_id: t.id
                for t in RT.tasks.values()
                if t.pending_approval_id
            }
            for p in pending:
                p["task_id"] = by_approval.get(p["approval_id"])
            return self._json(200, {"pending": pending})
        if path == "/api/models/recommend":
            try:
                return self._json(200, recommendation_bundle())
            except Exception:
                hw = probe_hardware()
                return self._json(200, {"ram_gb": hw.ram_gb, "vram_gb": hw.vram_gb, "profile": recommend(hw)})
        if path == "/api/models/status":
            try:
                return self._json(200, model_setup_status())
            except Exception as e:
                return self._json(500, {"error": str(e)})
        if path.startswith("/api/models/pull/"):
            job_id = path.rsplit("/", 1)[-1]
            job = get_job(job_id)
            if not job:
                return self._json(404, {"error": "job_not_found"})
            return self._json(200, job)
        if path == "/api/system/gpu":
            if gpu_as_api_dict is None:
                return self._json(200, {"error": "gpu_detect unavailable"})
            return self._json(200, gpu_as_api_dict())
        if path == "/api/setup/state":
            state = {"step": 1, "steps": [
                "welcome", "device", "profile", "privacy", "ai", "content",
                "sharing", "agents", "recovery", "provisioning", "tour"
            ]}
            if WIZARD_STATE.exists():
                state = json.loads(WIZARD_STATE.read_text(encoding="utf-8"))
            return self._json(200, state)
        if path == "/api/content/catalogue":
            try:
                cat = merge_catalogue_status(load_catalogue(_catalogue_file()), DATA)
                return self._json(200, cat)
            except Exception as e:
                return self._json(500, {"error": str(e)})
        if path == "/api/content/installed":
            return self._json(200, load_installed(DATA))
        if path == "/api/content/browse":
            roots = _pack_browse_roots()
            local = find_packs_on_paths([str(r) for r in roots if r != Path("/media")])
            usb = find_packs_on_paths(list_usb_pack_dirs())
            return self._json(200, {"local": local, "usb": usb})
        if path == "/api/content/preview":
            qs = parse_qs(urlparse(self.path).query)
            raw = (qs.get("path") or [""])[0]
            if not raw:
                return self._json(400, {"error": "path_required"})
            p = Path(raw)
            if not _pack_path_allowed(p):
                return self._json(403, {"error": "path_not_allowed"})
            if not p.is_file():
                return self._json(404, {"error": "pack_not_found"})
            try:
                meta = read_pack_metadata(p)
                compat = check_compatibility(meta["manifest"], DATA)
                return self._json(200, {**meta, "compat": compat})
            except PackError as e:
                return self._json(400, {"error": str(e)})
        if path == "/api/backup/list":
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            return self._json(200, {"backups": list_backups(BACKUP_DIR)})
        if path == "/api/updates/browse":
            local_roots = [UPDATE_INCOMING, UPDATE_BUNDLED, DATA / "updates"]
            local = find_update_bundles([str(r) for r in local_roots])
            usb = find_update_bundles(list_usb_pack_dirs())
            return self._json(200, {"local": local, "usb": usb})
        if path == "/api/updates/preview":
            qs = parse_qs(urlparse(self.path).query)
            raw = (qs.get("path") or [""])[0]
            if not raw:
                return self._json(400, {"error": "path_required"})
            p = Path(raw)
            if not _update_path_allowed(p):
                return self._json(403, {"error": "path_not_allowed"})
            if not p.is_file():
                return self._json(404, {"error": "bundle_not_found"})
            try:
                return self._json(200, read_bundle_metadata(p))
            except Exception as e:
                return self._json(400, {"error": str(e)})
        if path == "/api/updates/check":
            from updater import check_online_update, get_installed_version
            info = get_installed_version()
            result = check_online_update(info.get("version"), info.get("channel", "stable"))
            if result is None:
                return self._json(200, {"up_to_date": True, "version": info.get("version")})
            return self._json(200, result)
        if path == "/api/updates/download-status":
            status_file = Path("/srv/atlas/updates/staging/.progress")
            if status_file.is_file():
                try:
                    return self._json(200, json.loads(status_file.read_text()))
                except Exception:
                    pass
            return self._json(200, {"downloaded": 0, "total": 0, "done": False})
        if path == "/api/chat/threads":
            return self._json(200, {"threads": CHAT.list_threads(sess["username"])})
        if path.startswith("/api/chat/threads/"):
            thread_id = path.rsplit("/", 1)[-1]
            thread = CHAT.get_thread(sess["username"], thread_id)
            if not thread:
                return self._json(404, {"error": "thread_not_found"})
            return self._json(200, {"thread": thread})
        self._json(404, {"error": "not_found"})

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "bad_json"})

        if not path.startswith("/api/"):
            return self._json(404, {"error": "not_found"})

        ip = self._client_ip()

        if path == "/api/auth/bootstrap":
            if not AUTH.needs_bootstrap:
                audit_event({"event": "bootstrap", "result": "deny", "reason": "already_done", "ip": ip})
                return self._json(409, {"error": "bootstrap already completed"})
            try:
                AUTH.create_owner(data.get("username", ""), data.get("password", ""))
                tok, csrf = AUTH.login(data["username"], data["password"], ip=ip)
                audit_event({"event": "bootstrap", "result": "ok", "username": data["username"], "ip": ip})
                return self._json(
                    200,
                    {"ok": True, "username": data["username"]},
                    extra_headers=[
                        ("Set-Cookie", session_cookie_header(tok)),
                        ("Set-Cookie", csrf_cookie_header(csrf)),
                    ],
                )
            except Exception as e:
                audit_event({"event": "bootstrap", "result": "fail", "error": str(e), "ip": ip})
                return self._json(400, {"error": str(e)})

        if path == "/api/auth/login":
            try:
                tok, csrf = AUTH.login(data.get("username", ""), data.get("password", ""), ip=ip)
                audit_event({"event": "login", "result": "ok", "username": data.get("username"), "ip": ip})
                return self._json(
                    200,
                    {"ok": True},
                    extra_headers=[
                        ("Set-Cookie", session_cookie_header(tok)),
                        ("Set-Cookie", csrf_cookie_header(csrf)),
                    ],
                )
            except PermissionError as e:
                audit_event({"event": "login", "result": "fail", "username": data.get("username"), "ip": ip})
                return self._json(401, {"error": str(e)})
            except Exception as e:
                audit_event({"event": "login", "result": "fail", "error": str(e), "ip": ip})
                return self._json(401, {"error": str(e)})

        sess = self._require_auth(path, "POST")
        if sess is None:
            return
        if sess is True:
            return

        # CSRF on all authenticated state-changing requests
        if not self._require_csrf(sess):
            return

        if path == "/api/auth/logout":
            tok = self._session_token()
            if tok:
                AUTH.logout(tok)
            audit_event({"event": "logout", "result": "ok", "username": sess.get("username"), "ip": ip})
            return self._json(
                200,
                {"ok": True},
                extra_headers=[
                    ("Set-Cookie", clear_session_cookie()),
                    ("Set-Cookie", clear_csrf_cookie()),
                ],
            )

        if path == "/api/auth/reauth":
            # Stub: confirm password for sensitive ops (no privileged action yet).
            ok = AUTH.verify_password(sess["username"], data.get("password", ""))
            audit_event({
                "event": "reauth",
                "result": "ok" if ok else "fail",
                "username": sess["username"],
                "ip": ip,
            })
            if not ok:
                return self._json(401, {"error": "reauth_failed"})
            return self._json(200, {"ok": True, "confirmed": True})

        if path == "/api/ask":
            agent = data.get("agent", "atlas.guide")
            if agent not in RT.agents:
                return self._json(404, {"error": "unknown_agent"})
            history = data.get("history") or []
            if not isinstance(history, list):
                history = []
            task = RT.create_task(agent, data.get("prompt", ""), user_id=sess["username"])
            RT.plan(task.id)
            result = RT.run_step(task.id, history=history)
            audit_event({
                "event": "agent.ask",
                "agent": agent,
                "task_id": task.id,
                "state": task.state,
                "username": sess["username"],
            })
            return self._json(200, {"task_id": task.id, "state": task.state, "result": result})

        if path == "/api/chat/threads":
            agent = str(data.get("agent") or "atlas.guide")
            thread = CHAT.create_thread(sess["username"], agent=agent)
            audit_event({"event": "chat.create", "thread_id": thread["id"], "username": sess["username"]})
            return self._json(200, {"thread": thread})

        if path.startswith("/api/chat/threads/"):
            thread_id = path.rsplit("/", 1)[-1]
            messages = data.get("messages") if "messages" in data else None
            thread = CHAT.save_thread(
                sess["username"],
                thread_id,
                messages,
                agent=data.get("agent"),
                title=data.get("title"),
            )
            if not thread:
                return self._json(404, {"error": "thread_not_found"})
            return self._json(200, {"thread": thread})

        if path == "/api/models/pull":
            tag = (data.get("tag") or "").strip()
            catalog_id = (data.get("id") or "").strip()
            if not tag and catalog_id:
                from model_catalog import CATALOGUE

                for c in CATALOGUE:
                    if c["id"] == catalog_id:
                        tag = c["tag"]
                        break
            if not tag:
                return self._json(400, {"error": "tag_required"})
            try:
                job = start_pull(tag)
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            except RuntimeError as e:
                return self._json(503, {"error": str(e)})
            audit_event({
                "event": "models.pull",
                "tag": tag,
                "job_id": job.get("id"),
                "username": sess["username"],
            })
            return self._json(200, job)

        if path.startswith("/api/approvals/"):
            approval_id = path.rsplit("/", 1)[-1]
            if sess.get("role") not in {"owner", "admin"}:
                return self._json(403, {"error": "forbidden"})
            task_id = data.get("task_id")
            if not task_id:
                for t in RT.tasks.values():
                    if t.pending_approval_id == approval_id:
                        task_id = t.id
                        break
            if not task_id:
                return self._json(404, {"error": "task_not_found"})
            try:
                result = RT.approve(task_id, approval_id, approved=bool(data.get("approve", True)))
            except Exception as e:
                return self._json(400, {"error": str(e)})
            audit_event({
                "event": "agent.approval",
                "approval_id": approval_id,
                "task_id": task_id,
                "approve": bool(data.get("approve", True)),
                "username": sess["username"],
            })
            task = RT.tasks[task_id]
            return self._json(200, {"task_id": task_id, "state": task.state, "result": result})

        if path == "/api/knowledge/ingest":
            raw_path = data.get("path", "")
            if not raw_path:
                return self._json(400, {"error": "path_required"})
            p = Path(raw_path)
            if not _path_allowed(p, sess["username"]):
                return self._json(403, {"error": "path_not_allowed"})
            if not p.is_file():
                return self._json(404, {"error": "file_not_found"})
            if p.suffix.lower() not in INGEST_EXTENSIONS:
                return self._json(400, {"error": "unsupported_file_type"})
            try:
                rec = KS.ingest_file(sess["username"], p)
            except OSError as e:
                return self._json(400, {"error": str(e)})
            audit_event({
                "event": "knowledge.ingest",
                "path": str(p),
                "doc_id": rec.doc_id,
                "username": sess["username"],
            })
            return self._json(200, {
                "ok": True,
                "doc_id": rec.doc_id,
                "chunks": len(rec.chunks),
                "name": p.name,
                "path": str(p),
            })

        if path == "/api/knowledge/search":
            hits = KS.search(sess["username"], data.get("query", ""))
            return self._json(200, {"hits": hits})

        if path == "/api/knowledge/delete":
            doc_id = data.get("doc_id") or ""
            if not doc_id:
                return self._json(400, {"error": "doc_id_required"})
            ok = KS.delete_document(sess["username"], doc_id)
            if not ok:
                return self._json(404, {"error": "not_found"})
            audit_event({"event": "knowledge.delete", "doc_id": doc_id, "username": sess["username"]})
            return self._json(200, {"ok": True})

        if path == "/api/knowledge/backup":
            bak_root = DATA / "backups" / "knowledge"
            try:
                result = KS.backup(bak_root)
            except Exception as e:
                return self._json(500, {"error": str(e)})
            audit_event({"event": "knowledge.backup", "archive": result.get("archive"), "username": sess["username"]})
            return self._json(200, result)

        if path == "/api/knowledge/restore":
            archive = data.get("archive") or ""
            if not archive:
                return self._json(400, {"error": "archive_required"})
            p = Path(archive)
            bak_root = (DATA / "backups" / "knowledge").resolve()
            try:
                if not str(p.resolve()).startswith(str(bak_root)):
                    return self._json(403, {"error": "path_not_allowed"})
                result = KS.restore(p)
            except Exception as e:
                return self._json(400, {"error": str(e)})
            audit_event({"event": "knowledge.restore", "archive": str(p), "username": sess["username"]})
            return self._json(200, result)

        if path in {"/api/content/install", "/api/content/uninstall"}:
            if sess.get("role") not in {"owner", "admin"}:
                return self._json(403, {"error": "forbidden"})

        if path == "/api/content/install":
            pack_path: Path | None = None
            catalogue_id = data.get("catalogue_id") or ""
            raw_path = data.get("path") or ""
            if catalogue_id:
                pack_path = _resolve_catalogue_pack(catalogue_id)
                if not pack_path:
                    return self._json(404, {"error": "bundled_pack_not_found"})
            elif raw_path:
                pack_path = Path(raw_path)
                if not _pack_path_allowed(pack_path):
                    return self._json(403, {"error": "path_not_allowed"})
                if not pack_path.is_file():
                    return self._json(404, {"error": "pack_not_found"})
            else:
                return self._json(400, {"error": "path_or_catalogue_id_required"})
            prev = os.environ.get("ATLAS_ALLOW_UNSIGNED")
            os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
            try:
                result = install_pack(pack_path, DATA)
            except PackError as e:
                return self._json(400, {"error": str(e)})
            except Exception as e:
                return self._json(500, {"error": str(e)})
            finally:
                if prev is None:
                    os.environ.pop("ATLAS_ALLOW_UNSIGNED", None)
                else:
                    os.environ["ATLAS_ALLOW_UNSIGNED"] = prev
            audit_event({
                "event": "content.install",
                "pack_id": result.get("id"),
                "version": result.get("version"),
                "path": str(pack_path),
                "username": sess["username"],
            })
            return self._json(200, result)

        if path == "/api/content/uninstall":
            pack_id = data.get("id") or ""
            if not pack_id:
                return self._json(400, {"error": "id_required"})
            try:
                result = uninstall_pack(pack_id, DATA)
            except PackError as e:
                return self._json(400, {"error": str(e)})
            audit_event({
                "event": "content.uninstall",
                "pack_id": pack_id,
                "username": sess["username"],
            })
            return self._json(200, result)

        if path == "/api/updates/download":
            if sess.get("role") not in {"owner", "admin"}:
                return self._json(403, {"error": "forbidden"})
            url = data.get("url") or ""
            sha256 = data.get("sha256") or ""
            if not url:
                return self._json(400, {"error": "url_required"})
            staging = Path("/srv/atlas/updates/staging")
            staging.mkdir(parents=True, exist_ok=True)
            progress_file = staging / ".progress"
            # Drop stale bundles so a refreshed offer re-downloads cleanly.
            for old in staging.glob("*.atlas-update*"):
                old.unlink(missing_ok=True)
            progress_file.unlink(missing_ok=True)
            import threading
            from updater import download_bundle as _dl_bundle, UpdateError
            def _do_download():
                def _cb(downloaded, total):
                    try:
                        progress_file.write_text(json.dumps({"downloaded": downloaded, "total": total, "done": False}))
                    except OSError:
                        pass
                try:
                    dest = _dl_bundle(url, sha256, staging, progress_cb=_cb)
                    progress_file.write_text(json.dumps({"downloaded": 1, "total": 1, "done": True, "path": str(dest)}))
                except (UpdateError, Exception) as e:
                    progress_file.write_text(json.dumps({"done": True, "error": str(e)}))
            threading.Thread(target=_do_download, daemon=True).start()
            return self._json(202, {"status": "downloading"})

        if path in {"/api/backup/create", "/api/backup/restore", "/api/backup/verify", "/api/updates/apply"}:
            if sess.get("role") not in {"owner", "admin"}:
                return self._json(403, {"error": "forbidden"})

        if path == "/api/backup/create":
            passphrase = data.get("passphrase") or ""
            if not passphrase:
                return self._json(400, {"error": "passphrase_required"})
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            name = f"atlas-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.atlasbak"
            dest = BACKUP_DIR / name
            try:
                result = create_backup(DATA, dest, passphrase)
            except BackupError as e:
                return self._json(400, {"error": str(e)})
            audit_event({"event": "backup.create", "path": str(dest), "username": sess["username"]})
            return self._json(200, result)

        if path == "/api/backup/verify":
            raw_path = data.get("path") or ""
            p = Path(raw_path)
            if not _backup_path_allowed(p):
                return self._json(403, {"error": "path_not_allowed"})
            try:
                result = verify_backup(p)
            except BackupError as e:
                return self._json(400, {"error": str(e)})
            return self._json(200, result)

        if path == "/api/backup/restore":
            raw_path = data.get("path") or ""
            passphrase = data.get("passphrase") or ""
            p = Path(raw_path)
            if not _backup_path_allowed(p):
                return self._json(403, {"error": "path_not_allowed"})
            try:
                result = restore_backup(p, DATA, passphrase)
            except BackupError as e:
                return self._json(400, {"error": str(e)})
            audit_event({"event": "backup.restore", "path": str(p), "username": sess["username"]})
            return self._json(200, result)

        if path == "/api/updates/apply":
            raw_path = data.get("path") or ""
            p = Path(raw_path)
            if not _update_path_allowed(p):
                return self._json(403, {"error": "path_not_allowed"})
            if not p.is_file():
                return self._json(404, {"error": "bundle_not_found"})
            import subprocess
            helper = HERE / "atlas-apply-update.py"
            cmd = [
                "systemd-run", "--wait", "--collect",
                "-p", "ProtectSystem=false",
                "-p", "ProtectHome=false",
                "/usr/bin/python3", str(helper), str(p),
            ]
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            except subprocess.TimeoutExpired:
                return self._json(500, {"error": "apply timed out", "ok": False})
            except OSError as e:
                return self._json(500, {"error": f"apply spawn failed: {e}", "ok": False})
            out = (proc.stdout or "").strip()
            if not out:
                err = (proc.stderr or "").strip() or f"apply exited {proc.returncode}"
                return self._json(500, {"error": err, "ok": False})
            try:
                body = json.loads(out)
            except json.JSONDecodeError:
                return self._json(500, {"error": "bad apply response", "ok": False})
            result_ok = bool(body.get("ok"))
            audit_event({
                "event": "update.apply",
                "path": str(p),
                "ok": result_ok,
                "rolled_back": body.get("rolled_back"),
                "version": body.get("version"),
                "username": sess["username"],
            })
            if not result_ok and "error" not in body:
                body["error"] = body.get("detail") or "apply failed"
            return self._json(200, body)

        if path == "/api/setup/advance":
            WIZARD_STATE.parent.mkdir(parents=True, exist_ok=True)
            state = {"step": 1, "steps": [
                "welcome", "device", "profile", "privacy", "ai", "content",
                "sharing", "agents", "recovery", "provisioning", "tour"
            ]}
            if WIZARD_STATE.exists():
                state = json.loads(WIZARD_STATE.read_text(encoding="utf-8"))
            state["step"] = min(len(state["steps"]), state.get("step", 1) + 1)
            WIZARD_STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")
            return self._json(200, state)

        if path == "/api/network/mode":
            # Privileged path goes through system daemon — stub client here.
            return self._json(501, {
                "error": "use_system_daemon",
                "hint": "network.mode.apply via atlas-system-daemon socket",
            })

        self._json(404, {"error": "not_found"})

    def do_DELETE(self):  # noqa: N802
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return self._json(404, {"error": "not_found"})
        sess = self._require_auth(path, "DELETE")
        if sess is None or sess is True:
            return
        if not self._require_csrf(sess):
            return
        if path.startswith("/api/chat/threads/"):
            thread_id = path.rsplit("/", 1)[-1]
            if not CHAT.delete_thread(sess["username"], thread_id):
                return self._json(404, {"error": "thread_not_found"})
            audit_event({"event": "chat.delete", "thread_id": thread_id, "username": sess["username"]})
            return self._json(200, {"ok": True})
        return self._json(404, {"error": "not_found"})

    def log_message(self, fmt, *args):  # noqa: A003
        sys.stderr.write("atlas-cc: " + (fmt % args) + "\n")


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "databases").mkdir(parents=True, exist_ok=True)
    (DATA / "logs").mkdir(parents=True, exist_ok=True)
    (DATA / "knowledge").mkdir(parents=True, exist_ok=True)
    (DATA / "chat").mkdir(parents=True, exist_ok=True)
    (DATA / "backups" / "knowledge").mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    UPDATE_INCOMING.mkdir(parents=True, exist_ok=True)
    (DATA / "snapshots").mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Atlas Command Centre on http://{HOST}:{PORT}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
