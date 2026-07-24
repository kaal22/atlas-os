#!/usr/bin/env python3
"""Atlas Command Centre — local API + UI on 127.0.0.1:8787."""
from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import sys
import tarfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import request as urlrequest
from urllib.error import URLError
from urllib.parse import parse_qs, unquote, urlparse

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
    fetch_expand_bundle_for_manifest,
    fetch_map_tiles_for_manifest,
    fetch_zim_for_manifest,
    FetchCancelledError,
    find_packs_on_paths,
    has_usable_map_tiles,
    install_pack,
    list_usb_pack_dirs,
    load_catalogue,
    load_installed,
    maps_skip_fetch_env,
    merge_catalogue_status,
    read_content_expand_progress,
    read_maps_fetch_progress,
    read_pack_metadata,
    read_pmtiles_header,
    read_zim_fetch_progress,
    reindex_maps,
    repair_maps_registry,
    request_cancel_maps_fetch,
    request_cancel_zim_fetch,
    should_auto_expand_content,
    should_auto_fetch_zim,
    uninstall_pack,
    validate_pmtiles_archive,
    write_content_expand_progress,
    write_maps_fetch_progress,
    write_zim_fetch_progress,
    _pack_slug,
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
SYSTEM_SOCK = Path(os.environ.get("ATLAS_SYSTEM_SOCK", "/run/atlas/system.sock"))

SETUP_STEPS = ["welcome", "device", "ai", "content", "sharing", "agents", "recovery"]
DEFAULT_WIZARD: dict[str, Any] = {
    "step": 1,
    "steps": list(SETUP_STEPS),
    "choices": {
        "network_mode": None,
        "default_agent": "atlas.guide",
        "model_tag": None,
        "content_ids": [],
    },
    "completed": False,
    "updated_at": None,
}

# Public API paths (no session required)
PUBLIC_GET = {"/api/auth/bootstrap"}
PUBLIC_POST = {"/api/auth/login", "/api/auth/bootstrap"}


def audit_event(event: dict[str, Any]) -> None:
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    payload = {**event, "ts": datetime.now(timezone.utc).isoformat(), "source": "command_centre"}
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def _default_wizard() -> dict[str, Any]:
    return json.loads(json.dumps(DEFAULT_WIZARD))


def load_wizard_state() -> dict[str, Any]:
    state = _default_wizard()
    if WIZARD_STATE.is_file():
        try:
            raw = json.loads(WIZARD_STATE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                state["step"] = int(raw.get("step") or 1)
                if isinstance(raw.get("steps"), list) and raw["steps"]:
                    # Migrate old 11-step names to MVP 7-step list
                    if set(raw["steps"]) == set(SETUP_STEPS) or len(raw["steps"]) == 7:
                        state["steps"] = list(raw["steps"])
                    else:
                        state["steps"] = list(SETUP_STEPS)
                        # Map old step index roughly into new length
                        old_n = max(1, len(raw["steps"]))
                        state["step"] = max(1, min(7, round(state["step"] * 7 / old_n)))
                if isinstance(raw.get("choices"), dict):
                    state["choices"] = {**state["choices"], **raw["choices"]}
                state["completed"] = bool(raw.get("completed"))
                state["updated_at"] = raw.get("updated_at")
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass
    state["step"] = max(1, min(len(state["steps"]), int(state.get("step") or 1)))
    return state


def save_wizard_state(state: dict[str, Any]) -> dict[str, Any]:
    out = _default_wizard()
    out["step"] = max(1, min(len(SETUP_STEPS), int(state.get("step") or 1)))
    out["steps"] = list(SETUP_STEPS)
    choices = state.get("choices") if isinstance(state.get("choices"), dict) else {}
    out["choices"] = {**out["choices"], **choices}
    out["completed"] = bool(state.get("completed"))
    out["updated_at"] = datetime.now(timezone.utc).isoformat()
    WIZARD_STATE.parent.mkdir(parents=True, exist_ok=True)
    WIZARD_STATE.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out


def call_system_daemon(method: str, params: dict[str, Any] | None = None, ttl_sec: int = 60) -> dict[str, Any]:
    """JSON-line RPC to atlas-system-daemon over AF_UNIX."""
    import socket

    if not SYSTEM_SOCK.exists():
        return {"ok": False, "error": "system_daemon_unavailable", "detail": str(SYSTEM_SOCK)}
    token = GW.issue_token(method, ttl_sec=ttl_sec)
    req = {"method": method, "token": token, "params": params or {}}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(15)
            sock.connect(str(SYSTEM_SOCK))
            sock.sendall((json.dumps(req) + "\n").encode("utf-8"))
            data = b""
            while not data.endswith(b"\n"):
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
        if not data:
            return {"ok": False, "error": "empty_daemon_response"}
        return json.loads(data.decode("utf-8"))
    except (OSError, json.JSONDecodeError, TimeoutError) as e:
        return {"ok": False, "error": "daemon_rpc_failed", "detail": str(e)}


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
    ("kolibri", "http://127.0.0.1:8083/"),
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

VIEWER_CANDIDATES = [
    Path("/usr/share/atlas/maps-viewer"),
    PACKAGES / "atlas-maps-viewer" / "usr" / "share" / "atlas" / "maps-viewer",
]
BASE_ASSETS_TAR_CANDIDATES = [
    Path("/usr/share/atlas/nomad-map-assets/base-assets.tar.gz"),
    PACKAGES / "atlas-maps-viewer" / "usr" / "share" / "atlas" / "nomad-map-assets" / "base-assets.tar.gz",
]
_BASEMAP_ASSETS_LOCK = threading.Lock()
_COUNTRY_CODE_RE = re.compile(r"^[a-z]{2}$")


def maps_dir() -> Path:
    """Always derive from current DATA (tests / tooling may reassign DATA at runtime)."""
    return Path(DATA) / "maps"


# Back-compat alias; prefer maps_dir() so DATA reassignment cannot desync serve vs fetch.
MAPS_DIR = maps_dir()


def _viewer_root() -> Path | None:
    for cand in VIEWER_CANDIDATES:
        if (cand / "index.html").is_file():
            return cand
    return None


# Protomaps basemap v4 vector source-layer ids (paint-first + pretty styles).
PROTOMAPS_V4_LAYERS = (
    "earth",
    "water",
    "landcover",
    "landuse",
    "roads",
    "buildings",
    "boundaries",
    "places",
    "pois",
)


def maps_diag_payload() -> dict:
    """JSON for GET /maps/diag — viewer, assets, ready countries, sample tile header."""
    root = _viewer_root()
    app_js = (root / "lib" / "atlas-maps-app.js") if root else None
    assets = ensure_maps_basemap_assets()
    glyph = (assets / "fonts" / "Noto Sans Regular" / "0-255.pbf") if assets else None
    sprite_v4 = (assets / "sprites" / "v4" / "light.json") if assets else None
    sprite_v3 = (assets / "sprites" / "v3" / "light.json") if assets else None

    countries: dict[str, Any] = {}
    reg = maps_dir() / "countries.json"
    if reg.is_file():
        try:
            doc = json.loads(reg.read_text(encoding="utf-8"))
            raw = doc.get("countries") if isinstance(doc, dict) else None
            if isinstance(raw, dict):
                for cc, row in raw.items():
                    tile = resolve_country_pmtiles(str(cc).lower())
                    countries[str(cc).lower()] = {
                        "status": (row or {}).get("status") if isinstance(row, dict) else None,
                        "tiles_ok": tile is not None,
                        "tiles_path": str(tile) if tile else None,
                        "tiles_bytes": tile.stat().st_size if tile and tile.is_file() else None,
                    }
            elif isinstance(raw, list):
                for row in raw:
                    if not isinstance(row, dict) or not row.get("code"):
                        continue
                    cc = str(row["code"]).lower()
                    tile = resolve_country_pmtiles(cc)
                    countries[cc] = {
                        "status": row.get("status"),
                        "tiles_ok": tile is not None,
                        "tiles_path": str(tile) if tile else None,
                        "tiles_bytes": tile.stat().st_size if tile and tile.is_file() else None,
                    }
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    # Also probe common codes even if registry is sparse.
    for cc in ("uk", "ie", "de", "fr", "us"):
        if cc in countries:
            continue
        tile = resolve_country_pmtiles(cc)
        if tile:
            countries[cc] = {
                "status": "discovered",
                "tiles_ok": True,
                "tiles_path": str(tile),
                "tiles_bytes": tile.stat().st_size if tile.is_file() else None,
            }

    sample_header = None
    uk = resolve_country_pmtiles("uk")
    if uk and uk.is_file():
        try:
            sample_header = read_pmtiles_header(uk)
        except Exception:  # noqa: BLE001
            sample_header = None

    app_stat = None
    if app_js and app_js.is_file():
        st = app_js.stat()
        app_stat = {
            "path": str(app_js),
            "bytes": st.st_size,
            "mtime": int(st.st_mtime),
            "has_paint_first": "paint-first" in app_js.read_text(encoding="utf-8", errors="ignore"),
        }

    return {
        "ok": bool(root and app_js and app_js.is_file()),
        "viewer_root": str(root) if root else None,
        "atlas_maps_app": app_stat,
        "basemap_assets": {
            "path": str(assets) if assets else None,
            "glyphs_ok": bool(glyph and glyph.is_file()),
            "sprites_v4_ok": bool(sprite_v4 and sprite_v4.is_file()),
            "sprites_v3_ok": bool(sprite_v3 and sprite_v3.is_file()),
        },
        "expected_protomaps_v4_layers": list(PROTOMAPS_V4_LAYERS),
        "countries": countries,
        "uk_pmtiles_header": sample_header,
        "hints": [
            "Open http://127.0.0.1:8787/maps/?country=uk&debug=1",
            "Default style is pretty Protomaps (v4). Use &paint=1 for bright diagnostic fills.",
            "Vector source id is 'protomaps' (not country code). Red bbox = MapLibre OK.",
            "Command Centre serves viewer from /usr/share/atlas/maps-viewer (not NOMAD /srv copy).",
        ],
    }


def _resolve_under(root: Path, rel: str) -> Path | None:
    """Resolve rel under root; reject path traversal."""
    if not rel or rel.startswith("/") or "\\" in rel:
        return None
    root = root.resolve()
    try:
        target = (root / rel).resolve()
    except OSError:
        return None
    if root != target and root not in target.parents:
        return None
    return target


def ensure_maps_basemap_assets() -> Path | None:
    """Extract Protomaps fonts/sprites into maps/basemaps-assets when missing."""
    root = maps_dir()
    dest = root / "basemaps-assets"
    if dest.is_dir() and any(dest.iterdir()):
        return dest
    # Prefer already-synced NOMAD copy if present
    nomad_assets = DATA / "nomad-storage" / "maps" / "basemaps-assets"
    if nomad_assets.is_dir() and any(nomad_assets.iterdir()):
        try:
            root.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(nomad_assets, dest)
            return dest
        except OSError:
            pass
    tar_path = next((p for p in BASE_ASSETS_TAR_CANDIDATES if p.is_file()), None)
    if not tar_path:
        return dest if dest.is_dir() else None
    with _BASEMAP_ASSETS_LOCK:
        if dest.is_dir() and any(dest.iterdir()):
            return dest
        tmp = root / ".basemaps-assets.tmp"
        try:
            root.mkdir(parents=True, exist_ok=True)
            if tmp.exists():
                shutil.rmtree(tmp)
            tmp.mkdir(parents=True)
            with tarfile.open(tar_path, "r:gz") as tf:
                # Tar root is tozip/; strip so basemaps-assets/ lands under tmp/
                for member in tf.getmembers():
                    name = member.name
                    if name.startswith("tozip/"):
                        name = name[len("tozip/") :]
                    if not name or name.endswith("/"):
                        continue
                    if ".." in Path(name).parts:
                        continue
                    member.name = name
                    tf.extract(member, path=tmp)
            extracted = tmp / "basemaps-assets"
            if not extracted.is_dir():
                return None
            if dest.exists():
                shutil.rmtree(dest)
            extracted.rename(dest)
            shutil.rmtree(tmp, ignore_errors=True)
            return dest
        except (OSError, tarfile.TarError):
            shutil.rmtree(tmp, ignore_errors=True)
            return dest if dest.is_dir() else None


def resolve_country_pmtiles(cc: str) -> Path | None:
    cc = (cc or "").lower().strip()
    if not _COUNTRY_CODE_RE.match(cc):
        return None

    def _usable(p: Path) -> bool:
        ok, _reason = validate_pmtiles_archive(p)
        return ok

    root = maps_dir()
    country_dir = root / cc
    preferred = country_dir / f"{cc}.pmtiles"
    if _usable(preferred):
        return preferred
    if country_dir.is_dir():
        candidates = sorted(country_dir.glob("*.pmtiles"))
        usable = [p for p in candidates if _usable(p)]
        if len(usable) == 1:
            return usable[0]
    # Fallback: path recorded in countries.json (handles remapped / legacy installs)
    reg = root / "countries.json"
    if reg.is_file():
        try:
            doc = json.loads(reg.read_text(encoding="utf-8"))
            row = (doc.get("countries") or {}).get(cc) if isinstance(doc, dict) else None
            if isinstance(row, dict):
                recorded = Path(str(row.get("path") or ""))
                if recorded.is_dir():
                    cand = recorded / f"{cc}.pmtiles"
                    if _usable(cand):
                        return cand
                    extras = [p for p in recorded.glob("*.pmtiles") if _usable(p)]
                    if len(extras) == 1:
                        return extras[0]
        except (json.JSONDecodeError, OSError, TypeError):
            pass
    # Fallback: NOMAD publish layout
    nomad = DATA / "nomad-storage" / "maps" / "pmtiles" / f"{cc}.pmtiles"
    if _usable(nomad):
        return nomad.resolve() if nomad.is_symlink() else nomad
    return None


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

    def _guess_type(self, path: Path) -> str:
        ext = path.suffix.lower()
        known = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".pbf": "application/x-protobuf",
            ".pmtiles": "application/octet-stream",
            ".woff": "font/woff",
            ".woff2": "font/woff2",
            ".txt": "text/plain; charset=utf-8",
        }
        if ext in known:
            return known[ext]
        guessed, _ = mimetypes.guess_type(str(path))
        return guessed or "application/octet-stream"

    def _send_file(self, path: Path, *, content_type: str | None = None, cache: str = "public, max-age=3600") -> None:
        if not path.is_file():
            return self._json(404, {"error": "not_found"})
        try:
            size = path.stat().st_size
        except OSError:
            return self._json(404, {"error": "not_found"})
        ctype = content_type or self._guess_type(path)
        start, end = 0, size - 1
        status = 200
        range_hdr = self.headers.get("Range") or ""
        if range_hdr.startswith("bytes=") and size > 0:
            spec = range_hdr[6:].strip().split(",")[0].strip()
            if "-" in spec:
                left, right = spec.split("-", 1)
                try:
                    if left == "" and right != "":
                        suffix = int(right)
                        start = max(0, size - suffix)
                        end = size - 1
                    else:
                        start = int(left) if left else 0
                        end = int(right) if right else size - 1
                    if start < 0 or end < start or start >= size:
                        self.send_response(416)
                        self.send_header("Content-Range", f"bytes */{size}")
                        self.end_headers()
                        return
                    end = min(end, size - 1)
                    status = 206
                except ValueError:
                    start, end = 0, size - 1
                    status = 200
        length = 0 if size == 0 else (end - start + 1)
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        if cache:
            self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command == "HEAD" or length == 0:
            return
        with path.open("rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remaining -= len(chunk)

    def _serve_maps(self, path: str) -> bool:
        """Serve Atlas-native MapLibre viewer + PMTiles under /maps/*. Returns True if handled."""
        # Trailing slash required so relative asset URLs resolve under /maps/ (not /).
        if path == "/maps":
            q = urlparse(self.path).query
            loc = "/maps/" + (("?" + q) if q else "")
            self.send_response(301)
            self.send_header("Location", loc)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True
        if path in ("/maps/", "/maps/index.html"):
            root = _viewer_root()
            if not root:
                self._json(404, {"error": "maps_viewer_missing"})
                return True
            ensure_maps_basemap_assets()
            self._send_file(root / "index.html", cache="no-store")
            return True
        if path == "/maps/diag":
            # Public JSON diagnostics — blank-map triage without browser console.
            self._json(200, maps_diag_payload(), extra_headers=[("Cache-Control", "no-store")])
            return True
        if path == "/maps/countries.json":
            ensure_maps_basemap_assets()
            # Repair stub/missing registry entries when usable PMTiles already exist.
            try:
                repair_maps_registry(DATA)
            except Exception:  # noqa: BLE001
                pass
            reg = maps_dir() / "countries.json"
            if not reg.is_file():
                nomad_reg = DATA / "nomad-storage" / "maps" / "countries.json"
                if nomad_reg.is_file():
                    reg = nomad_reg
                else:
                    body = b'{"countries":{},"updated_at":0}\n'
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                    if self.command != "HEAD":
                        self.wfile.write(body)
                    return True
            self._send_file(reg, content_type="application/json", cache="no-store")
            return True
        if path.startswith("/maps/pmtiles/"):
            name = unquote(path[len("/maps/pmtiles/") :])
            if "/" in name or "\\" in name or ".." in name:
                self._json(400, {"error": "invalid_path"})
                return True
            if not name.endswith(".pmtiles"):
                self._json(404, {"error": "not_found"})
                return True
            cc = name[: -len(".pmtiles")].lower()
            tile = resolve_country_pmtiles(cc)
            if not tile:
                # Last chance: repair registry + retry resolve (stale stub / missed sync).
                try:
                    repair_maps_registry(DATA)
                except Exception:  # noqa: BLE001
                    pass
                tile = resolve_country_pmtiles(cc)
            if not tile:
                self._json(404, {"error": "tiles_not_ready", "country": cc})
                return True
            self._send_file(tile, content_type="application/octet-stream", cache="public, max-age=300")
            return True
        if path.startswith("/maps/basemaps-assets/"):
            assets = ensure_maps_basemap_assets()
            if not assets:
                self._json(404, {"error": "basemap_assets_missing"})
                return True
            rel = unquote(path[len("/maps/basemaps-assets/") :])
            target = _resolve_under(assets, rel)
            if not target or not target.is_file():
                self._json(404, {"error": "not_found"})
                return True
            self._send_file(target, cache="public, max-age=86400")
            return True
        if path.startswith("/maps/"):
            root = _viewer_root()
            if not root:
                self._json(404, {"error": "maps_viewer_missing"})
                return True
            rel = unquote(path[len("/maps/") :])
            target = _resolve_under(root, rel)
            if not target or not target.is_file():
                self._json(404, {"error": "not_found"})
                return True
            # App boot JS must not be sticky-cached — stale builds cause selector-only blank maps.
            name = target.name.lower()
            cache = "no-store" if name in ("atlas-maps-app.js", "index.html") or name.endswith(".html") else "public, max-age=86400"
            self._send_file(target, cache=cache)
            return True
        return False

    def do_HEAD(self):  # noqa: N802
        path = urlparse(self.path).path
        if path == "/maps" or path.startswith("/maps/"):
            if self._serve_maps(path):
                return
        self.send_response(404)
        self.end_headers()

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

        if path == "/maps" or path.startswith("/maps/"):
            if self._serve_maps(path):
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
            state = load_wizard_state()
            live: dict[str, Any] = {}
            try:
                live["model"] = model_setup_status()
            except Exception as e:
                live["model"] = {"error": str(e)}
            try:
                live["recommend"] = recommendation_bundle()
            except Exception:
                try:
                    hw = probe_hardware()
                    live["recommend"] = {"ram_gb": hw.ram_gb, "vram_gb": hw.vram_gb, "profile": recommend(hw)}
                except Exception as e:
                    live["recommend"] = {"error": str(e)}
            try:
                if gpu_as_api_dict is not None:
                    live["gpu"] = gpu_as_api_dict()
            except Exception:
                pass
            agents = []
            for a in RT.agents.values():
                agents.append({
                    "id": a.id,
                    "name": a.name,
                    "purpose": a.purpose,
                    "model_profile": a.model_profile,
                })
            live["agents"] = agents
            try:
                cat = merge_catalogue_status(load_catalogue(_catalogue_file()), DATA)
                live["catalogue"] = cat
            except Exception as e:
                live["catalogue"] = {"error": str(e), "packs": []}
            net = call_system_daemon("network.mode.read")
            live["network"] = net if net.get("ok") else {
                "ok": False,
                "mode": "private_device",
                "error": net.get("error"),
            }
            return self._json(200, {**state, "live": live})
        if path == "/api/network/mode":
            result = call_system_daemon("network.mode.read")
            if not result.get("ok"):
                # Soft-fail so wizard Sharing step still works offline from daemon
                return self._json(200, {"ok": False, "mode": "private_device", "error": result.get("error")})
            return self._json(200, result)
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
            channel = info.get("channel", "stable")
            current = info.get("version")
            result = check_online_update(current, channel)
            if result is None:
                return self._json(
                    200,
                    {
                        "up_to_date": True,
                        "version": current,
                        "current_version": current,
                        "channel": channel,
                    },
                )
            if isinstance(result, dict):
                result.setdefault("current_version", current)
                result.setdefault("channel", channel)
            return self._json(200, result)
        if path == "/api/updates/download-status":
            status_file = Path("/srv/atlas/updates/staging/.progress")
            if status_file.is_file():
                try:
                    return self._json(200, json.loads(status_file.read_text()))
                except Exception:
                    pass
            return self._json(200, {"downloaded": 0, "total": 0, "done": False})
        if path == "/api/content/maps-fetch-status":
            qs = parse_qs(urlparse(self.path).query)
            country = (qs.get("country") or [""])[0].strip().lower() or None
            return self._json(200, read_maps_fetch_progress(DATA, country))
        if path == "/api/content/maps-repair":
            try:
                return self._json(200, repair_maps_registry(DATA))
            except Exception as e:  # noqa: BLE001
                return self._json(500, {"ok": False, "error": str(e)})
        if path == "/api/content/zim-fetch-status":
            qs = parse_qs(urlparse(self.path).query)
            pack_slug = (qs.get("pack") or qs.get("pack_slug") or [""])[0].strip().lower() or None
            pack_id = (qs.get("id") or qs.get("pack_id") or [""])[0].strip() or None
            if pack_id and not pack_slug:
                pack_slug = pack_id.rsplit(".", 1)[-1].lower()
            return self._json(200, read_zim_fetch_progress(DATA, pack_slug))
        if path == "/api/content/expand-fetch-status":
            qs = parse_qs(urlparse(self.path).query)
            pack_slug = (qs.get("pack") or qs.get("pack_slug") or [""])[0].strip().lower() or None
            pack_id = (qs.get("id") or qs.get("pack_id") or [""])[0].strip() or None
            if pack_id and not pack_slug:
                pack_slug = pack_id.rsplit(".", 1)[-1].lower()
            return self._json(200, read_content_expand_progress(DATA, pack_slug))
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
            fetch_tiles = data.get("fetch_tiles")
            if fetch_tiles is None:
                fetch_tiles = True
            async_tiles = bool(data.get("async_tiles", True))
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

            # Size warning for large packs (maps tiles / Wikipedia ZIM). UI confirms; API can force.
            if catalogue_id and not data.get("confirm_large"):
                cat = load_catalogue(_catalogue_file())
                entry = next((p for p in cat.get("packs") or [] if p.get("id") == catalogue_id), None)
                if entry and entry.get("size_class") == "large" and not data.get("force"):
                    return self._json(
                        409,
                        {
                            "error": "large_pack_confirm_required",
                            "size_warning": entry.get("size_warning"),
                            "size_hint_bytes": entry.get("size_hint_bytes"),
                            "licence_note": entry.get("licence_note"),
                        },
                    )

            prev = os.environ.get("ATLAS_ALLOW_UNSIGNED")
            os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
            try:
                # Install stub first; optionally fetch tiles/ZIM in background.
                result = install_pack(pack_path, DATA, fetch_tiles=False)
            except PackError as e:
                return self._json(400, {"error": str(e)})
            except Exception as e:
                return self._json(500, {"error": str(e)})
            finally:
                if prev is None:
                    os.environ.pop("ATLAS_ALLOW_UNSIGNED", None)
                else:
                    os.environ["ATLAS_ALLOW_UNSIGNED"] = prev

            want_fetch = bool(fetch_tiles) and (
                (result.get("type") or "") == "atlas.content.map"
                or str(result.get("type") or "").endswith(".map")
            )
            if want_fetch and maps_skip_fetch_env():
                want_fetch = False
                result["tiles_status"] = "stub"
                result["tiles_fetch"] = "skipped"
                result["tiles_fetch_note"] = "ATLAS_MAPS_SKIP_FETCH is set"
            if want_fetch:
                target_path = Path(result["target"])
                # Only skip fetch when real usable tiles already exist (≥64 KiB PMTiles).
                if has_usable_map_tiles(target_path):
                    want_fetch = False
                    result["tiles_status"] = "ready"
            if want_fetch and async_tiles:
                country = ""
                try:
                    meta_path = Path(result["target"]) / "manifest.json"
                    if meta_path.is_file():
                        manifest = json.loads(meta_path.read_text(encoding="utf-8"))
                    else:
                        manifest = read_pack_metadata(pack_path)["manifest"]
                    country = str((manifest.get("meta") or {}).get("country") or Path(result["target"]).name)
                    meta = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
                    tiles_cfg = meta.get("tiles_fetch") if isinstance(meta.get("tiles_fetch"), dict) else {}
                    hint = int(
                        tiles_cfg.get("size_hint_bytes")
                        or meta.get("size_hint_bytes")
                        or 0
                    )
                    result["tiles_size_hint_bytes"] = hint

                    def _do_fetch(m=manifest, tgt=Path(result["target"]), cc=country):
                        try:
                            tile_info = fetch_map_tiles_for_manifest(m, tgt, DATA)
                            reindex_maps(m, tgt, DATA)
                            repair_maps_registry(DATA)
                            write_maps_fetch_progress(
                                DATA,
                                {
                                    "country": cc,
                                    "status": "ready",
                                    "done": True,
                                    "downloaded": tile_info.get("bytes") or 0,
                                    "total": tile_info.get("bytes") or 0,
                                    "path": tile_info.get("path"),
                                    "licence": tile_info.get("licence"),
                                    "message": "Tiles ready offline",
                                },
                                cc,
                            )
                        except FetchCancelledError:
                            pass
                        except Exception as e:  # noqa: BLE001
                            if read_maps_fetch_progress(DATA, cc).get("status") == "cancelled":
                                return
                            write_maps_fetch_progress(
                                DATA,
                                {
                                    "country": cc,
                                    "status": "error",
                                    "done": True,
                                    "error": str(e),
                                    "message": "Pack installed; tile download failed — retry from Content",
                                },
                                cc,
                            )

                    write_maps_fetch_progress(
                        DATA,
                        {
                            "country": country,
                            "status": "starting",
                            "done": False,
                            "downloaded": 0,
                            "total": hint,
                            "pack_id": manifest.get("id"),
                            "message": "Starting map tile download…",
                        },
                        country,
                    )
                    threading.Thread(target=_do_fetch, daemon=True).start()
                    result["tiles_status"] = "fetching"
                    result["tiles_fetch"] = "started"
                except Exception as e:  # noqa: BLE001
                    result["tiles_fetch_error"] = str(e)
                    result["tiles_status"] = "stub"
            elif want_fetch and not async_tiles:
                try:
                    meta_path = Path(result["target"]) / "manifest.json"
                    manifest = json.loads(meta_path.read_text(encoding="utf-8"))
                    tile_info = fetch_map_tiles_for_manifest(manifest, Path(result["target"]), DATA)
                    reindex_maps(manifest, Path(result["target"]), DATA)
                    result["tiles"] = tile_info
                    result["tiles_status"] = "ready" if has_usable_map_tiles(Path(result["target"])) else "stub"
                except PackError as e:
                    result["tiles_fetch_error"] = str(e)
                    result["tiles_status"] = "stub"

            # Wikipedia / knowledge ZIM async fetch (mirrors maps tiles_fetch).
            try:
                meta_path = Path(result["target"]) / "manifest.json"
                if meta_path.is_file():
                    manifest = json.loads(meta_path.read_text(encoding="utf-8"))
                else:
                    manifest = read_pack_metadata(pack_path)["manifest"]
                tgt = Path(result["target"])
                if should_auto_fetch_zim(manifest, tgt):
                    slug = _pack_slug(manifest, tgt)
                    hint = int(
                        ((manifest.get("meta") or {}).get("zim_fetch") or {}).get("size_hint_bytes")
                        or (manifest.get("meta") or {}).get("size_hint_bytes")
                        or 0
                    )

                    def _do_zim(m=manifest, t=tgt, s=slug):
                        try:
                            zim_info = fetch_zim_for_manifest(m, t, DATA)
                            write_zim_fetch_progress(
                                DATA,
                                {
                                    "pack_id": m.get("id"),
                                    "pack_slug": s,
                                    "status": "ready",
                                    "done": True,
                                    "downloaded": zim_info.get("bytes") or 0,
                                    "total": zim_info.get("bytes") or 0,
                                    "path": zim_info.get("path"),
                                    "kiwix_path": zim_info.get("kiwix_path"),
                                    "licence": zim_info.get("licence"),
                                    "message": "ZIM ready offline (Kiwix)",
                                },
                                s,
                            )
                        except FetchCancelledError:
                            pass
                        except Exception as e:  # noqa: BLE001
                            if read_zim_fetch_progress(DATA, s).get("status") == "cancelled":
                                return
                            write_zim_fetch_progress(
                                DATA,
                                {
                                    "pack_id": m.get("id"),
                                    "pack_slug": s,
                                    "status": "error",
                                    "done": True,
                                    "error": str(e),
                                    "message": "Pack installed; ZIM download failed — retry from Content",
                                },
                                s,
                            )

                    # Publish progress before the worker starts so the UI can poll immediately.
                    write_zim_fetch_progress(
                        DATA,
                        {
                            "pack_id": manifest.get("id"),
                            "pack_slug": slug,
                            "status": "starting",
                            "done": False,
                            "downloaded": 0,
                            "total": hint,
                            "message": "Starting ZIM download…",
                        },
                        slug,
                    )
                    threading.Thread(target=_do_zim, daemon=True).start()
                    result["zim_status"] = "fetching"
                    result["zim_fetch"] = "started"
                    result["zim_pack_slug"] = slug
                    result["zim_size_hint_bytes"] = hint
                elif (manifest.get("meta") or {}).get("zim_fetch"):
                    zims = list(tgt.rglob("*.zim")) if tgt.is_dir() else []
                    result["zim_status"] = "ready" if zims else "pending"

                if should_auto_expand_content(manifest, tgt):
                    slug = _pack_slug(manifest, tgt)

                    def _do_expand(m=manifest, t=tgt, s=slug):
                        try:
                            fetch_expand_bundle_for_manifest(m, t, DATA)
                        except Exception as e:  # noqa: BLE001
                            write_content_expand_progress(
                                DATA,
                                {
                                    "pack_id": m.get("id"),
                                    "pack_slug": s,
                                    "status": "error",
                                    "done": True,
                                    "error": str(e),
                                    "message": "Expand download failed — retry from Content",
                                },
                                s,
                            )

                    threading.Thread(target=_do_expand, daemon=True).start()
                    result["expand_status"] = "fetching"
                    result["expand_pack_slug"] = slug
            except Exception as e:  # noqa: BLE001
                result["zim_fetch_error"] = str(e)

            audit_event({
                "event": "content.install",
                "pack_id": result.get("id"),
                "version": result.get("version"),
                "path": str(pack_path),
                "tiles_status": result.get("tiles_status"),
                "zim_status": result.get("zim_status"),
                "username": sess["username"],
            })
            return self._json(200, result)

        if path == "/api/content/fetch-tiles":
            if sess.get("role") not in {"owner", "admin"}:
                return self._json(403, {"error": "forbidden"})
            pack_id = data.get("id") or data.get("catalogue_id") or ""
            country = (data.get("country") or "").strip().lower()
            installed = load_installed(DATA).get("packs") or []
            match = None
            if pack_id:
                match = next((p for p in installed if p.get("id") == pack_id), None)
            elif country:
                match = next(
                    (p for p in installed if str(p.get("target") or "").rstrip("/").endswith("/" + country)),
                    None,
                )
            if not match:
                return self._json(404, {"error": "pack_not_installed"})
            target = Path(match["target"])
            manifest_path = target / "manifest.json"
            if not manifest_path.is_file():
                return self._json(400, {"error": "manifest_missing_on_target"})
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                return self._json(400, {"error": str(e)})
            cc = str((manifest.get("meta") or {}).get("country") or target.name)

            def _retry_fetch(m=manifest, tgt=target, ccode=cc):
                try:
                    tile_info = fetch_map_tiles_for_manifest(m, tgt, DATA)
                    reindex_maps(m, tgt, DATA)
                    repair_maps_registry(DATA)
                    write_maps_fetch_progress(
                        DATA,
                        {
                            "country": ccode,
                            "status": "ready",
                            "done": True,
                            "downloaded": tile_info.get("bytes") or 0,
                            "total": tile_info.get("bytes") or 0,
                            "path": tile_info.get("path"),
                        },
                        ccode,
                    )
                except FetchCancelledError:
                    pass
                except Exception as e:  # noqa: BLE001
                    if read_maps_fetch_progress(DATA, ccode).get("status") == "cancelled":
                        return
                    write_maps_fetch_progress(
                        DATA,
                        {"country": ccode, "status": "error", "done": True, "error": str(e)},
                        ccode,
                    )

            write_maps_fetch_progress(
                DATA,
                {
                    "country": cc,
                    "status": "starting",
                    "done": False,
                    "downloaded": 0,
                    "total": int(
                        ((manifest.get("meta") or {}).get("tiles_fetch") or {}).get("size_hint_bytes")
                        or (manifest.get("meta") or {}).get("size_hint_bytes")
                        or 0
                    ),
                    "pack_id": match.get("id"),
                    "message": "Retrying map tile download…",
                },
                cc,
            )
            threading.Thread(target=_retry_fetch, daemon=True).start()
            return self._json(
                202,
                {
                    "status": "fetching",
                    "id": match.get("id"),
                    "country": cc,
                    "tiles_status": "fetching",
                    "tiles_size_hint_bytes": int(
                        ((manifest.get("meta") or {}).get("tiles_fetch") or {}).get("size_hint_bytes")
                        or (manifest.get("meta") or {}).get("size_hint_bytes")
                        or 0
                    ),
                    "target": str(target),
                },
            )

        if path == "/api/content/fetch-zim":
            if sess.get("role") not in {"owner", "admin"}:
                return self._json(403, {"error": "forbidden"})
            pack_id = data.get("id") or data.get("catalogue_id") or ""
            installed = load_installed(DATA).get("packs") or []
            match = next((p for p in installed if p.get("id") == pack_id), None) if pack_id else None
            if not match:
                return self._json(404, {"error": "pack_not_installed"})
            target = Path(match["target"])
            manifest_path = target / "manifest.json"
            if not manifest_path.is_file():
                return self._json(400, {"error": "manifest_missing_on_target"})
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                return self._json(400, {"error": str(e)})
            slug = _pack_slug(manifest, target)
            hint = int(
                ((manifest.get("meta") or {}).get("zim_fetch") or {}).get("size_hint_bytes")
                or (manifest.get("meta") or {}).get("size_hint_bytes")
                or 0
            )

            def _retry_zim(m=manifest, tgt=target, s=slug):
                try:
                    zim_info = fetch_zim_for_manifest(m, tgt, DATA)
                    write_zim_fetch_progress(
                        DATA,
                        {
                            "pack_id": m.get("id"),
                            "pack_slug": s,
                            "status": "ready",
                            "done": True,
                            "downloaded": zim_info.get("bytes") or 0,
                            "total": zim_info.get("bytes") or 0,
                            "path": zim_info.get("path"),
                            "kiwix_path": zim_info.get("kiwix_path"),
                            "message": "ZIM ready offline (Kiwix)",
                        },
                        s,
                    )
                except FetchCancelledError:
                    pass
                except Exception as e:  # noqa: BLE001
                    if read_zim_fetch_progress(DATA, s).get("status") == "cancelled":
                        return
                    write_zim_fetch_progress(
                        DATA,
                        {
                            "pack_id": m.get("id"),
                            "pack_slug": s,
                            "status": "error",
                            "done": True,
                            "error": str(e),
                            "message": "ZIM download failed — retry from Content",
                        },
                        s,
                    )

            write_zim_fetch_progress(
                DATA,
                {
                    "pack_id": match.get("id"),
                    "pack_slug": slug,
                    "status": "starting",
                    "done": False,
                    "downloaded": 0,
                    "total": hint,
                    "message": "Retrying ZIM download…",
                },
                slug,
            )
            threading.Thread(target=_retry_zim, daemon=True).start()
            return self._json(
                202,
                {
                    "status": "fetching",
                    "id": match.get("id"),
                    "pack_slug": slug,
                    "zim_pack_slug": slug,
                    "zim_status": "fetching",
                },
            )

        if path == "/api/content/cancel-maps-fetch":
            if sess.get("role") not in {"owner", "admin"}:
                return self._json(403, {"error": "forbidden"})
            country = (data.get("country") or "").strip().lower()
            pack_id = data.get("id") or data.get("catalogue_id") or ""
            if not country and pack_id:
                installed = load_installed(DATA).get("packs") or []
                match = next((p for p in installed if p.get("id") == pack_id), None)
                if match:
                    target = Path(match["target"])
                    manifest_path = target / "manifest.json"
                    if manifest_path.is_file():
                        try:
                            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                            country = str((manifest.get("meta") or {}).get("country") or target.name).lower()
                        except (json.JSONDecodeError, OSError):
                            pass
            if not country:
                return self._json(400, {"error": "country_required"})
            result = request_cancel_maps_fetch(DATA, country, pack_id=pack_id or None)
            code = 200 if result.get("ok") else 409
            return self._json(code, result)

        if path == "/api/content/cancel-zim-fetch":
            if sess.get("role") not in {"owner", "admin"}:
                return self._json(403, {"error": "forbidden"})
            pack_slug = (data.get("pack") or data.get("pack_slug") or "").strip().lower()
            pack_id = data.get("id") or data.get("catalogue_id") or ""
            if not pack_slug and pack_id:
                pack_slug = pack_id.rsplit(".", 1)[-1].lower()
            if not pack_slug and pack_id:
                installed = load_installed(DATA).get("packs") or []
                match = next((p for p in installed if p.get("id") == pack_id), None)
                if match:
                    target = Path(match["target"])
                    manifest_path = target / "manifest.json"
                    if manifest_path.is_file():
                        try:
                            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                            pack_slug = _pack_slug(manifest, target)
                        except (json.JSONDecodeError, OSError):
                            pass
            if not pack_slug:
                return self._json(400, {"error": "pack_slug_required"})
            result = request_cancel_zim_fetch(DATA, pack_slug, pack_id=pack_id or None)
            code = 200 if result.get("ok") else 409
            return self._json(code, result)

        if path == "/api/content/fetch-expand":
            if sess.get("role") not in {"owner", "admin"}:
                return self._json(403, {"error": "forbidden"})
            pack_id = data.get("id") or data.get("catalogue_id") or ""
            installed = load_installed(DATA).get("packs") or []
            match = next((p for p in installed if p.get("id") == pack_id), None) if pack_id else None
            if not match:
                return self._json(404, {"error": "pack_not_installed"})
            target = Path(match["target"])
            manifest_path = target / "manifest.json"
            if not manifest_path.is_file():
                return self._json(400, {"error": "manifest_missing_on_target"})
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                return self._json(400, {"error": str(e)})
            slug = _pack_slug(manifest, target)

            def _retry_expand(m=manifest, tgt=target, s=slug):
                try:
                    fetch_expand_bundle_for_manifest(m, tgt, DATA)
                except Exception as e:  # noqa: BLE001
                    write_content_expand_progress(
                        DATA,
                        {
                            "pack_id": m.get("id"),
                            "pack_slug": s,
                            "status": "error",
                            "done": True,
                            "error": str(e),
                            "message": "Expand download failed — retry from Content",
                        },
                        s,
                    )

            threading.Thread(target=_retry_expand, daemon=True).start()
            return self._json(202, {"status": "fetching", "id": match.get("id"), "pack_slug": slug})

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
            for old in staging.glob("*"):
                if old.name == ".progress":
                    continue
                if old.is_file() or old.is_symlink():
                    old.unlink(missing_ok=True)
            progress_file.unlink(missing_ok=True)
            from updater import download_bundle as _dl_bundle, UpdateError
            def _do_download():
                def _cb(downloaded, total):
                    try:
                        progress_file.write_text(json.dumps({"downloaded": downloaded, "total": total, "done": False}))
                    except OSError:
                        pass
                try:
                    dest = _dl_bundle(
                        url,
                        sha256,
                        staging,
                        progress_cb=_cb,
                        expected_size=int(data.get("size") or data.get("bundle_size") or 0),
                    )
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
            result_file = Path("/srv/atlas/updates/staging/.apply-result.json")
            result_file.unlink(missing_ok=True)
            cmd = [
                "systemd-run", "--wait", "--collect", "--pipe",
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
            body = None
            if result_file.is_file():
                try:
                    body = json.loads(result_file.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    pass
            if body is None:
                out = (proc.stdout or "").strip()
                if out:
                    try:
                        body = json.loads(out)
                    except json.JSONDecodeError:
                        pass
            if body is None:
                err = (proc.stderr or "").strip() or f"apply exited {proc.returncode}"
                return self._json(500, {"error": err, "ok": False})
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

        if path == "/api/setup/save":
            state = load_wizard_state()
            if "step" in data:
                try:
                    state["step"] = int(data["step"])
                except (TypeError, ValueError):
                    pass
            if isinstance(data.get("choices"), dict):
                state["choices"] = {**state.get("choices", {}), **data["choices"]}
            if "completed" in data:
                state["completed"] = bool(data["completed"])
            saved = save_wizard_state(state)
            audit_event({
                "event": "setup.save",
                "step": saved.get("step"),
                "completed": saved.get("completed"),
                "username": sess["username"],
            })
            return self._json(200, saved)

        if path == "/api/setup/advance":
            state = load_wizard_state()
            state["step"] = min(len(state["steps"]), int(state.get("step") or 1) + 1)
            if isinstance(data.get("choices"), dict):
                state["choices"] = {**state.get("choices", {}), **data["choices"]}
            if data.get("completed"):
                state["completed"] = True
            saved = save_wizard_state(state)
            return self._json(200, saved)

        if path == "/api/network/mode":
            if sess.get("role") not in {"owner", "admin"}:
                return self._json(403, {"error": "forbidden"})
            mode = (data.get("mode") or "").strip()
            if mode == "later":
                state = load_wizard_state()
                state.setdefault("choices", {})["network_mode"] = "later"
                save_wizard_state(state)
                return self._json(200, {"ok": True, "mode": "later", "skipped": True})
            if mode not in {"private_device", "trusted_lan", "private_hotspot", "offline_isolation"}:
                return self._json(400, {"error": "invalid_mode"})
            # Daemon gates non-live modes on role == "owner" + owner_confirmed.
            # Treat Command Centre admin the same as owner for this apply path.
            sess_role = sess.get("role") or ""
            daemon_role = "owner" if sess_role in {"owner", "admin"} else sess_role
            result = call_system_daemon(
                "network.mode.apply",
                {
                    "mode": mode,
                    "role": daemon_role,
                    "owner_confirmed": daemon_role == "owner",
                },
            )
            if result.get("ok"):
                state = load_wizard_state()
                state.setdefault("choices", {})["network_mode"] = mode
                save_wizard_state(state)
                audit_event({
                    "event": "network.mode.apply",
                    "mode": mode,
                    "username": sess["username"],
                    "dry_run": result.get("dry_run"),
                })
                return self._json(200, result)
            # Daemon missing: still persist wizard intent so setup can finish offline.
            if result.get("error") in {"system_daemon_unavailable", "daemon_rpc_failed"}:
                state = load_wizard_state()
                state.setdefault("choices", {})["network_mode"] = mode
                save_wizard_state(state)
                return self._json(200, {
                    "ok": False,
                    "deferred": True,
                    "mode": mode,
                    "error": result.get("error"),
                    "detail": result.get("detail"),
                })
            return self._json(400, result)

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
