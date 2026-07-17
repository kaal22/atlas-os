#!/usr/bin/env python3
"""Atlas Command Centre — local API + UI on 127.0.0.1:8787."""
from __future__ import annotations

import json
import os
import sys
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
    apply_update,
    find_update_bundles,
    read_bundle_metadata,
)

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


def probe_services() -> dict[str, Any]:
    """Loopback HTTP probes — no subprocess (CC security boundary)."""
    services: list[dict[str, Any]] = []
    for name, url in SERVICE_SPECS:
        ok = False
        http = 0
        try:
            req = urlrequest.Request(url, method="GET")
            with urlrequest.urlopen(req, timeout=2) as resp:
                http = int(getattr(resp, "status", 200))
                ok = True
        except URLError:
            pass
        except Exception:
            pass
        services.append({"name": name, "url": url, "ok": ok, "http": http})
    return {"services": services}


# Raw string: JS/CSS backslashes must reach the browser unchanged.
UI = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Atlas Command Centre</title>
<style>
:root{--bg:#071525;--panel:#0b1f33;--accent:#3db8a0;--text:#e8eef5;--muted:#9bb0c4}
*{box-sizing:border-box}body{margin:0;font-family:Georgia,"Iowan Old Style",serif;background:linear-gradient(165deg,#071525,#102a44);color:var(--text);min-height:100vh}
header{padding:1.25rem 1.5rem;border-bottom:1px solid rgba(61,184,160,.25);display:flex;justify-content:space-between;align-items:center}
.brand{font-size:1.6rem;font-weight:700;letter-spacing:.04em}.brand span{color:var(--accent)}
nav a{color:var(--muted);margin-left:1rem;text-decoration:none;font-family:system-ui,sans-serif;font-size:.9rem}
nav a:hover{color:var(--accent)}
main{display:grid;grid-template-columns:220px 1fr;gap:1rem;padding:1rem 1.5rem;max-width:1100px;margin:0 auto}
aside{background:rgba(11,31,51,.7);padding:1rem;border-radius:2px;height:fit-content}
aside button{display:block;width:100%;text-align:left;background:transparent;border:0;color:var(--text);padding:.55rem .4rem;cursor:pointer;font:inherit}
aside button.active{color:var(--accent)}
section{background:rgba(11,31,51,.55);padding:1.25rem;border-radius:2px;min-height:420px}
h1{font-size:1.4rem;margin:0 0 .5rem}p,li{color:var(--muted);line-height:1.5}
input,textarea,select{width:100%;background:#071525;border:1px solid rgba(61,184,160,.35);color:var(--text);padding:.55rem;margin:.35rem 0 .75rem;font:inherit}
textarea{min-height:100px}
.btn{background:var(--accent);color:#042018;border:0;padding:.55rem 1rem;cursor:pointer;font-weight:700}
.btn.secondary{background:transparent;color:var(--accent);border:1px solid var(--accent);margin-left:.5rem}
.btn:disabled{opacity:.45;cursor:not-allowed}
.pre{white-space:pre-wrap;background:#071525;padding:.75rem;font-family:ui-monospace,monospace;font-size:.85rem;color:var(--text)}
.download-panel{border:1px solid rgba(61,184,160,.45);background:rgba(7,21,37,.85);padding:1rem 1.25rem;margin:1rem 0}
.download-panel h2{margin:0 0 .75rem;font-size:1rem;color:var(--accent)}
.download-row{margin:.65rem 0}
.download-row .label{font-size:.9rem;margin-bottom:.35rem;display:flex;justify-content:space-between;gap:1rem}
.progress-track{height:10px;background:#071525;border:1px solid rgba(61,184,160,.25);border-radius:2px;overflow:hidden}
.progress-fill{height:100%;background:var(--accent);width:0%;transition:width .35s ease}
.download-msg{font-size:.85rem;color:var(--muted);margin-top:.35rem;font-family:ui-monospace,monospace}
.download-msg.ok{color:var(--accent)}.download-msg.err{color:#ffb4b4}
.spinner{display:inline-block;width:1rem;height:1rem;border:2px solid rgba(61,184,160,.25);border-top-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite;vertical-align:middle;margin-right:.35rem}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes pulse{from{opacity:.35}to{opacity:1}}
.chat-wrap{display:flex;flex-direction:column;height:min(520px,60vh);border:1px solid rgba(61,184,160,.25);background:#071525;margin:1rem 0}
.chat-log{flex:1;overflow-y:auto;padding:1rem;display:flex;flex-direction:column;gap:.75rem}
.bubble{max-width:85%;padding:.65rem .85rem;border-radius:4px;line-height:1.45;font-size:.95rem;white-space:pre-wrap;word-break:break-word}
.bubble.user{align-self:flex-end;background:rgba(61,184,160,.22);color:var(--text)}
.bubble.assistant{align-self:flex-start;background:rgba(255,255,255,.06);color:var(--text)}
.bubble.system{align-self:center;background:transparent;color:var(--muted);font-size:.85rem;font-style:italic}
.bubble.err{align-self:flex-start;background:rgba(255,100,100,.12);color:#ffb4b4;border:1px solid rgba(255,100,100,.35)}
.cite-box{margin-top:.5rem;padding:.5rem .65rem;border-left:2px solid var(--accent);background:rgba(61,184,160,.08);font-size:.8rem;color:var(--muted)}
.cite-box a{color:var(--accent);cursor:pointer;text-decoration:underline}
.cite-link{font-size:.85rem}
.source-viewer{border:1px solid rgba(61,184,160,.35);background:#071525;padding:1rem;margin-top:.75rem;max-height:240px;overflow-y:auto;white-space:pre-wrap;font-size:.9rem;color:var(--text)}
.chat-input{display:flex;gap:.5rem;padding:.75rem;border-top:1px solid rgba(61,184,160,.2);align-items:flex-end}
.chat-input textarea{flex:1;min-height:2.5rem;margin:0;resize:vertical}
.approval-banner{display:none;margin:.75rem 0;padding:.75rem 1rem;border:1px solid #c97858;background:rgba(201,120,88,.12)}
.approval-banner.show{display:block}
.card{border:1px solid rgba(61,184,160,.3);background:rgba(7,21,37,.6);padding:1rem 1.1rem;margin:.75rem 0;border-radius:2px}
.card h3{margin:0 0 .4rem;font-size:1.05rem;color:var(--text)}
.card p{margin:.35rem 0;font-size:.9rem}
.card .tools{font-size:.8rem;color:var(--muted);font-family:ui-monospace,monospace}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
@media(max-width:760px){.grid-2{grid-template-columns:1fr}}
.file-browser{border:1px solid rgba(61,184,160,.25);background:#071525;min-height:220px;max-height:320px;overflow-y:auto}
.file-row{display:flex;justify-content:space-between;align-items:center;padding:.5rem .75rem;border-bottom:1px solid rgba(255,255,255,.06);cursor:pointer;font-size:.9rem}
.file-row:hover{background:rgba(61,184,160,.1)}
.file-row.selected{background:rgba(61,184,160,.2)}
.file-row .meta{color:var(--muted);font-size:.8rem}
.breadcrumb{font-size:.85rem;color:var(--muted);margin:.5rem 0 .75rem;font-family:ui-monospace,monospace}
.breadcrumb a{color:var(--accent);cursor:pointer;text-decoration:none}
.msg{padding:.65rem .85rem;margin:.75rem 0;border-radius:2px;font-size:.9rem}
.msg.ok{background:rgba(61,184,160,.15);color:var(--accent);border:1px solid rgba(61,184,160,.35)}
.msg.err{background:rgba(255,100,100,.12);color:#ffb4b4;border:1px solid rgba(255,100,100,.35)}
.msg.info{background:rgba(255,255,255,.05);color:var(--muted)}
.stat-row{display:flex;justify-content:space-between;padding:.4rem 0;border-top:1px solid rgba(61,184,160,.15);font-size:.9rem}
.stat-row:first-child{border-top:0}
.pill-sm{font-size:.75rem;padding:.15rem .45rem;border-radius:2px;text-transform:uppercase;letter-spacing:.04em}
.pill-sm.ok{background:rgba(61,184,160,.2);color:var(--accent)}
.pill-sm.bad{background:rgba(255,100,100,.15);color:#ffb4b4}
.hidden{display:none}
#gate{max-width:420px;margin:4rem auto;padding:1.5rem;background:rgba(11,31,51,.75)}
#gate h1{margin-top:0}
</style></head><body>
<div id="gate">
  <h1>Create owner account</h1>
  <p>First-run setup. Choose a username and a strong password. There is no default account.</p>
  <p id="gateStatus" style="color:var(--muted);font-size:.9rem">Starting…</p>
  <div id="gateForm">
    <input id="bu" placeholder="username" autocomplete="username" />
    <input id="bp" type="password" placeholder="password" autocomplete="new-password" />
    <input id="bp2" type="password" placeholder="confirm password" autocomplete="new-password" />
    <button class="btn" type="button" onclick="doBootstrap()">Create owner</button>
    <p id="berr" style="color:#ffb4b4"></p>
  </div>
</div>
<div id="app" class="hidden">
<header><div class="brand">Atlas <span>OS</span></div><nav>
<a href="#/ask">Chat</a><a href="#/models">Models</a><a href="#/agents">Agents</a><a href="#/knowledge">Knowledge</a>
<a href="#/content">Content</a><a href="#/system">System</a><a href="#/setup">Setup</a>
<a href="#" id="logoutLink">Logout</a></nav></header>
<main>
<aside id="side"></aside>
<section id="view"></section>
</main>
</div>
<noscript><p style="color:#fff;padding:2rem;text-align:center">JavaScript is required for Atlas Command Centre.</p></noscript>
<script>
/* Auth bootstrap — keep tiny and dependency-free so first-user setup always works */
function csrf(){
  var m=document.cookie.match(/(?:^|; )atlas_csrf=([^;]*)/);
  return m?decodeURIComponent(m[1]):'';
}
function api(path,opts){
  opts=opts||{};
  var method=(opts.method||'GET').toUpperCase();
  var headers=Object.assign({'Content-Type':'application/json'}, opts.headers||{});
  if(method!=='GET' && method!=='HEAD'){
    var t=csrf();
    if(t) headers['X-CSRF-Token']=t;
  }
  return fetch(path,Object.assign({},opts,{headers:headers,credentials:'same-origin'})).then(function(r){
    return r.text().then(function(txt){
      var body={};
      try{body=txt?JSON.parse(txt):{};}catch(e){body={error:'bad_response'};}
      body._status=r.status;
      return body;
    });
  });
}
function doBootstrap(){
  var bu=document.getElementById('bu');
  var bp=document.getElementById('bp');
  var bp2=document.getElementById('bp2');
  var berr=document.getElementById('berr');
  if(!bu||!bp||!bp2){alert('Form not ready');return;}
  if(bp.value!==bp2.value){if(berr)berr.textContent='Passwords do not match';return;}
  if(berr)berr.textContent='Creating account…';
  api('/api/auth/bootstrap',{method:'POST',body:JSON.stringify({username:bu.value,password:bp.value})}).then(function(r){
    if(r.error){if(berr)berr.textContent=r.error;return;}
    location.hash='#/home';
    if(typeof boot==='function') boot();
    else location.reload();
  }).catch(function(e){
    if(berr)berr.textContent='Failed: '+(e&&e.message?e.message:e);
  });
}
function doLogin(){
  var u=document.getElementById('u');
  var p=document.getElementById('p');
  var lerr=document.getElementById('lerr');
  if(!u||!p){alert('Form not ready');return;}
  if(lerr)lerr.textContent='Signing in…';
  api('/api/auth/login',{method:'POST',body:JSON.stringify({username:u.value,password:p.value})}).then(function(r){
    if(r.error){if(lerr)lerr.textContent=r.error;return;}
    location.hash='#/home';
    if(typeof boot==='function') boot();
    else location.reload();
  }).catch(function(e){
    if(lerr)lerr.textContent='Failed: '+(e&&e.message?e.message:e);
  });
}
</script>
<script>
function csrf(){
  const m=document.cookie.match(/(?:^|; )atlas_csrf=([^;]*)/);
  return m?decodeURIComponent(m[1]):'';
}
async function api(path,opts={}){
  const method=(opts.method||'GET').toUpperCase();
  const headers=Object.assign({'Content-Type':'application/json'}, opts.headers||{});
  if(method!=='GET' && method!=='HEAD'){
    const t=csrf();
    if(t) headers['X-CSRF-Token']=t;
  }
  const r=await fetch(path,{...opts,headers,credentials:'same-origin'});
  let body={};
  try{body=await r.json();}catch(e){body={error:'bad_response'};}
  body._status=r.status;
  return body;
}
const gate=document.getElementById('gate');
const app=document.getElementById('app');
const view=document.getElementById('view');
const side=document.getElementById('side');
let authed=false;
let _chatHistory=[];
let _kbPath='';
let _kbSelected='';

function setGateStatus(text){
  const el=document.getElementById('gateStatus');
  if(el) el.textContent=text||'';
}
function showBootstrapGate(status){
  app.classList.add('hidden');
  gate.classList.remove('hidden');
  gate.innerHTML=`<h1>Create owner account</h1>
      <p>First-run setup. Choose a username and a strong password. There is no default account.</p>
      <p id="gateStatus" style="color:var(--muted);font-size:.9rem">${status||''}</p>
      <div id="gateForm">
        <input id="bu" placeholder="username" autocomplete="username" />
        <input id="bp" type="password" placeholder="password" autocomplete="new-password" />
        <input id="bp2" type="password" placeholder="confirm password" autocomplete="new-password" />
        <button class="btn" type="button" onclick="doBootstrap()">Create owner</button>
        <p id="berr" style="color:#ffb4b4"></p>
      </div>`;
}
function showLoginGate(status){
  app.classList.add('hidden');
  gate.classList.remove('hidden');
  gate.innerHTML=`<h1>Sign in</h1>
      <p id="gateStatus" style="color:var(--muted);font-size:.9rem">${status||''}</p>
      <input id="u" placeholder="username" autocomplete="username" />
      <input id="p" type="password" placeholder="password" autocomplete="current-password" />
      <button class="btn" type="button" onclick="doLogin()">Login</button>
      <p id="lerr" style="color:#ffb4b4"></p>`;
}
function showGateError(msg){
  app.classList.add('hidden');
  gate.classList.remove('hidden');
  gate.innerHTML=`<h1>Command Centre</h1>
      <p class="msg err">${escapeHtml(msg||'Could not start. Is atlas-command-centre running?')}</p>
      <button class="btn" type="button" onclick="boot()">Retry</button>
      <p style="font-size:.85rem;color:var(--muted)">Also try <code>http://127.0.0.1:8787/</code> or check
      <code>systemctl status atlas-command-centre</code>.</p>`;
}

function showMsg(elId,text,kind){
  const el=document.getElementById(elId);
  if(!el) return;
  if(!text){el.innerHTML='';return;}
  el.innerHTML=`<div class="msg ${kind||'info'}">${escapeHtml(text)}</div>`;
}
function kbError(code){
  const m={
    path_required:'Choose a file first.',
    path_not_allowed:'That location is not allowed.',
    file_not_found:'File not found — it may have been moved.',
    unsupported_file_type:'This file type cannot be imported.',
    folder_not_found:'Folder not found.',
    not_a_directory:'That path is not a folder.',
  };
  return m[code]||code||'Something went wrong.';
}
function formatBytes(n){
  if(!n) return '';
  if(n<1024) return n+' B';
  if(n<1048576) return (n/1024).toFixed(1)+' KB';
  return (n/1048576).toFixed(1)+' MB';
}
function escapeHtml(s){
  return String(s==null?'':s)
    .split('&').join('&amp;')
    .split('<').join('&lt;')
    .split('>').join('&gt;')
    .split('"').join('&quot;');
}
function jsQuote(s){
  return encodeURIComponent(String(s==null?'':s));
}

function routes(){return [
  ['Home','home'],['Chat','ask'],['Models','models'],['Agents','agents'],['Knowledge','knowledge'],
  ['Content','content'],['System','system'],['Setup','setup']
];}
function renderNav(active){
  side.innerHTML=routes().map(([l,id])=>`<button class="${active===id?'active':''}" onclick="location.hash='#/${id}'">${l}</button>`).join('');
}

async function ensureSession(){
  setGateStatus('Checking device…');
  const bootResp=await api('/api/auth/bootstrap');
  if(bootResp._status>=500 || bootResp.error==='bad_response'){
    showGateError('Could not reach the Command Centre API (HTTP '+(bootResp._status||'?')+').');
    return false;
  }
  if(bootResp.needs_bootstrap){
    showBootstrapGate('');
    return false;
  }
  const me=await api('/api/auth/session');
  if(me._status===401 || me.error==='unauthorized'){
    showLoginGate('');
    return false;
  }
  if(me._status>=400){
    showGateError(me.error||('Session check failed (HTTP '+me._status+')'));
    return false;
  }
  gate.classList.add('hidden');
  app.classList.remove('hidden');
  authed=true;
  return true;
}

async function doLogout(){
  await api('/api/auth/logout',{method:'POST',body:'{}'});
  authed=false;
  boot();
}

async function page(){
  if(!authed) return;
  const id=(location.hash.replace('#/','')||'home');
  renderNav(id);
  if(id==='home'){
    const h=await api('/api/system/health');
    const m=await api('/api/models/status');
    const sv=await api('/api/system/services');
    const lib=await api('/api/knowledge/library');
    const banner=!m.ready?`<div style="border:1px solid var(--accent);padding:1rem;margin:1rem 0">
      <strong>Set up your AI model</strong>
      <p>${m.hint||'Download a model to start chatting.'}</p>
      <button class=btn onclick="location.hash='#/models'">Choose a model</button>
    </div>`:`<p style="color:var(--accent)">AI model ready — <a href="#/ask" style="color:var(--accent)">Open Chat →</a></p>`;
    const svcRows=(sv.services||[]).map(s=>
      `<div class="stat-row"><span>${escapeHtml(s.name)}</span>
        <span class="pill-sm ${s.ok?'ok':'bad'}">${s.ok?'running':'down'}</span></div>`).join('');
    const statusLabel=h.status==='ok'?'Healthy':(h.status==='degraded'?'Needs attention':'Unknown');
    const gpuNote=h.gpu_warning&&h.status==='ok'
      ?`<p class="msg info" style="margin-top:1rem">${escapeHtml(h.gpu_warning)}</p>`:'';
    view.innerHTML=`<h1>Welcome</h1>
      <p>Your private Atlas environment on this device.</p>
      ${banner}
      <div class="grid-2">
        <div class="card">
          <h3>Quick links</h3>
          <p><a href="#/ask" style="color:var(--accent)">Chat</a> ·
             <a href="#/models" style="color:var(--accent)">Models</a> ·
             <a href="#/knowledge" style="color:var(--accent)">Knowledge</a> ·
             <a href="#/content" style="color:var(--accent)">Content</a></p>
          <p><a href="http://127.0.0.1:8791/" style="color:var(--accent)">Service Check</a> (Kiwix, Ollama, NOMAD)</p>
        </div>
        <div class="card">
          <h3>Status</h3>
          <div class="stat-row"><span>System</span><span class="pill-sm ${h.status==='ok'?'ok':'bad'}">${statusLabel}</span></div>
          <div class="stat-row"><span>AI model</span><span class="pill-sm ${m.ready?'ok':'bad'}">${m.ready?'ready':'not installed'}</span></div>
          <div class="stat-row"><span>Your documents</span><span>${lib.count||0} indexed</span></div>
          <div class="stat-row"><span>Knowledge search</span><span class="pill-sm ${(h.knowledge&&h.knowledge.mode==='hybrid')?'ok':'bad'}">${(h.knowledge&&h.knowledge.mode)||'?'}</span></div>
        </div>
      </div>
      <h2 style="margin-top:1.25rem">Local services</h2>
      <div class="card">${svcRows||'<p>No service data yet.</p>'}</div>
      ${h.hint?`<p class="msg info" style="margin-top:1rem">${escapeHtml(h.hint)}</p>`:''}
      ${gpuNote}`;
    return;
  }
  if(id==='models'){
    await renderModels();
    return;
  }
  if(id==='ask'){
    const m=await api('/api/models/status');
    const need=!m.ready?`<div style="border:1px solid #c97858;padding:.75rem;margin-bottom:1rem">
      <strong>Download a model first</strong> — Ask needs a local chat model.
      <button class=btn onclick="location.hash='#/models'">Go to Models</button>
    </div>`:'';
    view.innerHTML=`${need}<h1>Chat</h1>
      <p style="margin-top:0;color:var(--muted)">Talk to Atlas Guide on this PC. Answers stay local.</p>
      <select id=agent onchange="_chatHistory=[];renderChatLog([])">
        <option value="atlas.guide">Atlas Guide</option>
        <option value="atlas.research">Research Agent</option>
        <option value="atlas.document">Document Agent</option>
        <option value="atlas.system-steward">System Steward</option>
      </select>
      <div class="approval-banner" id=approvalBanner></div>
      <div class="chat-wrap">
        <div class="chat-log" id=chatLog></div>
        <div class="chat-input">
          <textarea id=q placeholder="Type a message…" rows="2"></textarea>
          <button class=btn id=sendBtn onclick="ask()">Send</button>
        </div>
      </div>
      <details style="margin-top:.5rem;color:var(--muted);font-size:.85rem"><summary>Technical details</summary>
        <div class=pre id=out></div></details>`;
    renderChatLog(_chatHistory);
    refreshApprovals();
    const qEl=document.getElementById('q');
    if(qEl) qEl.addEventListener('keydown',e=>{
      if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();ask();}
    });
    return;
  }
  if(id==='agents'){
    const a=await api('/api/agents');
    const cards=(a.agents||[]).map(ag=>{
      const tools=(ag.tools||[]).join(', ')||'none';
      return `<div class="card">
        <h3>${escapeHtml(ag.name)}</h3>
        <p>${escapeHtml(ag.purpose)}</p>
        <p class="tools">Tools: ${escapeHtml(tools)}</p>
        <p style="font-size:.85rem;color:var(--muted)">Profile: ${escapeHtml(ag.model_profile||'light')}</p>
        <button class="btn" style="margin-top:.5rem" onclick="useAgentInChat(decodeURIComponent('${jsQuote(ag.id)}'))">Use in Chat</button>
      </div>`;
    }).join('');
    view.innerHTML=`<h1>Agents</h1>
      <p style="margin-top:0">Installed assistants on this Atlas device. Pick one in <a href="#/ask" style="color:var(--accent)">Chat</a> to talk.</p>
      ${cards||'<p class="msg info">No agents installed.</p>'}`;
    return;
  }
  if(id==='knowledge'){
    const st=await api('/api/knowledge/status');
    const mode=st.mode||'keyword';
    const kbHint=st.hint?`<div class="msg info">${escapeHtml(st.hint)}</div>`:'';
    const modeLine=`Search mode: <strong>${escapeHtml(mode)}</strong>`
      +(st.embed_ready?' · embeddings ready':' · embeddings not installed')
      +(st.qdrant?' · Qdrant up':' · Qdrant down');
    view.innerHTML=`<h1>Knowledge</h1>
      <p style="margin-top:0">Add your notes and documents so Atlas can search them locally.</p>
      <p style="font-size:.9rem;color:var(--muted)">${modeLine}</p>
      ${kbHint}
      <div class="grid-2">
        <div>
          <h2 style="font-size:1rem">Browse files</h2>
          <div class="breadcrumb" id=kbCrumb>Loading…</div>
          <div class="file-browser" id=kbList></div>
          <p style="font-size:.85rem;color:var(--muted);margin-top:.5rem">Supported: .md, .txt, .pdf, .csv, .json, .html, …</p>
        </div>
        <div>
          <h2 style="font-size:1rem">Import</h2>
          <div id=kbSelected class="msg info">Select a file from the list</div>
          <button class="btn" id=kbIngestBtn disabled onclick="ingestSelected()">Add to knowledge base</button>
          <div id=kbIngestMsg></div>
          <h2 style="font-size:1rem;margin-top:1.25rem">Your library</h2>
          <div id=kbLibrary class="file-browser" style="min-height:120px;max-height:180px"></div>
          <h2 style="font-size:1rem;margin-top:1.25rem">Source viewer</h2>
          <div id=kbSourceViewer class="source-viewer">Select a library entry or citation to read the passage.</div>
          <h2 style="font-size:1rem;margin-top:1.25rem">Backup</h2>
          <button class="btn secondary" onclick="backupKnowledge()">Snapshot knowledge</button>
          <div id=kbBackupMsg></div>
        </div>
      </div>
      <h2 style="margin-top:1.25rem">Search</h2>
      <div style="display:flex;gap:.5rem;align-items:center">
        <input id=sq placeholder="Search your indexed documents…" style="margin:0;flex:1" />
        <button class=btn onclick="searchKnowledge()">Search</button>
      </div>
      <div id=kbSearchResults style="margin-top:.75rem"></div>`;
    await loadKbBrowser();
    await loadKbLibrary();
    return;
  }
  if(id==='content'){
    await renderContent();
    return;
  }
  if(id==='system'){
    const hw=await api('/api/models/recommend');
    const gpu=await api('/api/system/gpu');
    const bak=await api('/api/backup/list');
    const upd=await api('/api/updates/browse');
    const warn=hw.warning?`<div class="msg err">${escapeHtml(hw.warning)}
      <br/><code>${escapeHtml(hw.install_command||'sudo atlas-gpu-setup --install-nvidia')}</code></div>`:'';
    const gpuLine=gpu.error?`<p class="msg info">${escapeHtml(gpu.error)}</p>`:
      `<div class="stat-row"><span>GPU</span><span>${escapeHtml(gpu.gpu_name||gpu.gpu||'none')}</span></div>
       <div class="stat-row"><span>VRAM</span><span>${gpu.vram_gb||0} GB</span></div>
       <div class="stat-row"><span>NVIDIA drivers</span><span class="pill-sm ${gpu.nvidia_driver_ok?'ok':'bad'}">${gpu.nvidia_driver_ok?'ok':'missing'}</span></div>`;
    const bakRows=(bak.backups||[]).map(b=>
      `<div class="stat-row"><span>${escapeHtml(b.name)}</span>
        <span>
          <span class="pill-sm ${b.verified?'ok':'bad'}">${b.verified?'ok':'bad'}</span>
          <button class="btn secondary" style="margin-left:.35rem" onclick="verifyBackup(decodeURIComponent('${jsQuote(b.path)}'))">Verify</button>
          <button class="btn" style="margin-left:.35rem" onclick="restoreBackupPrompt(decodeURIComponent('${jsQuote(b.path)}'))">Restore</button>
        </span></div>`).join('');
    const updRows=[...(upd.local||[]),...(upd.usb||[])].map(u=>
      `<div class="file-row" onclick="previewUpdate(decodeURIComponent('${jsQuote(u.path)}'))">
        <span>[update] ${escapeHtml(u.from_version||'?')} → ${escapeHtml(u.to_version||'?')}</span>
        <span class="meta">${escapeHtml(u.publisher||'')}</span>
      </div>`).join('');
    view.innerHTML=`<h1>System</h1>
      ${warn}
      <div class="card">
        <h3>AI profile</h3>
        <div class="stat-row"><span>Recommended profile</span><span><strong>${escapeHtml(hw.profile||'?')}</strong></span></div>
        <div class="stat-row"><span>RAM</span><span>${hw.ram_gb||'?'} GB</span></div>
        <div class="stat-row"><span>Reason</span><span style="max-width:55%;text-align:right">${escapeHtml(hw.profile_reason||'')}</span></div>
      </div>
      <div class="card">
        <h3>Graphics</h3>
        ${gpuLine}
        <p style="font-size:.85rem;margin-top:.75rem">Guide: <code>/usr/share/atlas/docs/GPU_SETUP.md</code></p>
      </div>
      <div class="card">
        <h3>Encrypted backup</h3>
        <p style="font-size:.9rem;color:var(--muted)">Backs up Atlas config, databases, knowledge, content manifests, and user data.</p>
        <input id=bakPass type=password placeholder="Passphrase" style="max-width:280px" />
        <button class=btn onclick="createFullBackup()">Create backup</button>
        <div id=bakMsg style="margin-top:.5rem"></div>
        <h4 style="margin-top:1rem">Existing backups</h4>
        ${bakRows||'<p class="msg info">No backups yet.</p>'}
      </div>
      <div class="card">
        <h3>Offline updates</h3>
        <p style="font-size:.9rem;color:var(--muted)">Import a signed .atlas-update bundle. Failed health checks roll back automatically.</p>
        <div class="file-browser" style="max-height:160px">${updRows||'<div class="msg info" style="margin:.5rem">No update bundles found.</div>'}</div>
        <div id=updPreview style="margin-top:.75rem;display:none"></div>
        <div id=updMsg style="margin-top:.5rem"></div>
      </div>
      <div class="card">
        <h3>Confirm sensitive action</h3>
        <p style="font-size:.9rem">Re-enter your password before privileged operations (future use).</p>
        <input id=rp type=password placeholder="Password" />
        <button class=btn onclick="reauth()">Confirm</button>
        <div id=reout style="margin-top:.5rem"></div>
      </div>`;
    return;
  }
  if(id==='setup'){
    const st=await api('/api/setup/state');
    const steps=st.steps||[];
    const step=st.step||1;
    const pct=steps.length?Math.round((step/steps.length)*100):0;
    const current=steps[step-1]||'welcome';
    view.innerHTML=`<h1>First-run setup</h1>
      <p>Step ${step} of ${steps.length}: <strong>${escapeHtml(current)}</strong></p>
      <div class="progress-track" style="margin:1rem 0"><div class="progress-fill" style="width:${pct}%"></div></div>
      <p style="color:var(--muted);font-size:.9rem">Complete the wizard to configure Atlas. You can return here anytime.</p>
      <button class=btn onclick="nextStep()">Next step</button>
      <details style="margin-top:1rem;color:var(--muted);font-size:.85rem"><summary>All steps</summary>
        <ol style="margin:.5rem 0;padding-left:1.25rem">${steps.map((s,i)=>
          `<li style="color:${i+1===step?'var(--accent)':'var(--muted)'}">${escapeHtml(s)}</li>`).join('')}</ol>
      </details>`;
  }
}
function useAgentInChat(agentId){
  location.hash='#/ask';
  setTimeout(()=>{
    const s=document.getElementById('agent');
    if(s) s.value=agentId;
    _chatHistory=[];
    renderChatLog([]);
  },50);
}
async function loadKbBrowser(){
  const q=_kbPath?`?path=${encodeURIComponent(_kbPath)}`:'';
  const b=await api('/api/knowledge/browse'+q);
  const crumb=document.getElementById('kbCrumb');
  const list=document.getElementById('kbList');
  if(!list) return;
  if(b.error){
    list.innerHTML=`<div class="msg err">${escapeHtml(kbError(b.error))}</div>`;
    return;
  }
  if(crumb){
    if(b.roots) crumb.innerHTML=`<a onclick="_kbPath='';loadKbBrowser()">Folders</a>`;
    else{
      const parts=[];
      if(b.parent!==null&&b.parent!==''){
        parts.push(`<a onclick="_kbPath=decodeURIComponent('${jsQuote(b.parent)}');_kbSelected='';loadKbBrowser()">Up</a>`);
      }else if(b.parent===''){
        parts.push(`<a onclick="_kbPath='';_kbSelected='';loadKbBrowser()">Folders</a>`);
      }
      parts.push(` <span>${escapeHtml(b.cwd||'')}</span>`);
      crumb.innerHTML=parts.join(' · ');
    }
  }
  const rows=(b.entries||[]).map(e=>{
    const icon=e.kind==='dir'?'[dir]':'[file]';
    const meta=e.kind==='file'?formatBytes(e.size):'folder';
    const sel=_kbSelected===e.path?' selected':'';
    const click=e.kind==='dir'
      ?`onclick="_kbPath=decodeURIComponent('${jsQuote(e.path)}');_kbSelected='';loadKbBrowser()"`
      :`onclick="selectKbFile(decodeURIComponent('${jsQuote(e.path)}'),decodeURIComponent('${jsQuote(e.name)}'))"`;
    return `<div class="file-row${sel}" data-path="${escapeHtml(e.path)}" ${click}>
      <span>${icon} ${escapeHtml(e.name)}</span><span class="meta">${meta}</span></div>`;
  }).join('');
  list.innerHTML=rows||'<div class="msg info" style="margin:.5rem">This folder is empty.</div>';
}
function selectKbFile(path,name){
  _kbSelected=path;
  const el=document.getElementById('kbSelected');
  const btn=document.getElementById('kbIngestBtn');
  if(el) el.innerHTML=`<strong>${escapeHtml(name)}</strong><br/><span style="font-size:.85rem;color:var(--muted)">${escapeHtml(path)}</span>`;
  if(btn) btn.disabled=false;
  document.querySelectorAll('.file-row').forEach(r=>{
    r.classList.toggle('selected',r.dataset.path===path);
  });
}
async function ingestSelected(){
  if(!_kbSelected) return;
  const btn=document.getElementById('kbIngestBtn');
  if(btn){btn.disabled=true;btn.textContent='Importing…';}
  showMsg('kbIngestMsg','','');
  const r=await api('/api/knowledge/ingest',{method:'POST',body:JSON.stringify({path:_kbSelected})});
  if(btn){btn.disabled=false;btn.textContent='Add to knowledge base';}
  if(r.error||!r.ok){
    showMsg('kbIngestMsg',kbError(r.error)||'Import failed','err');
    return;
  }
  showMsg('kbIngestMsg','Added '+r.name+' ('+r.chunks+' sections indexed).','ok');
  await loadKbLibrary();
}
async function loadKbLibrary(){
  const lib=await api('/api/knowledge/library');
  const el=document.getElementById('kbLibrary');
  if(!el) return;
  const docs=lib.documents||[];
  if(!docs.length){
    el.innerHTML='<div class="msg info" style="margin:.5rem">No documents yet — import a file above.</div>';
    return;
  }
  el.innerHTML=docs.map(d=>
    `<div class="file-row" onclick="openSource(decodeURIComponent('${jsQuote(d.doc_id)}'),0)">
      <span>[doc] ${escapeHtml(d.name)}</span>
      <span class="meta">${d.chunks} sections${d.vectorized?' · vec':''}</span>
    </div>`).join('');
}
async function searchKnowledge(){
  const q=(document.getElementById('sq')||{}).value||'';
  const el=document.getElementById('kbSearchResults');
  if(!q.trim()){showMsg('kbSearchResults','Enter a search term.','info');return;}
  const r=await api('/api/knowledge/search',{method:'POST',body:JSON.stringify({query:q})});
  const hits=r.hits||[];
  if(!hits.length){
    el.innerHTML='<div class="msg info">No matches in your library.</div>';
    return;
  }
  el.innerHTML=hits.map(h=>
    `<div class="card" style="margin:.5rem 0;cursor:pointer" onclick="openSource(decodeURIComponent('${jsQuote(h.doc_id)}'),${Number(h.chunk_index||0)})">
      <p style="margin:0;font-size:.8rem;color:var(--muted)">${escapeHtml(h.name||h.path||'')} · ${escapeHtml(h.source||'')}</p>
      <p style="margin:.35rem 0 0">${escapeHtml((h.text||'').slice(0,400))}${(h.text||'').length>400?'…':''}</p>
    </div>`).join('');
}
async function backupKnowledge(){
  showMsg('kbBackupMsg','Creating snapshot…','info');
  const r=await api('/api/knowledge/backup',{method:'POST',body:'{}'});
  if(r.error||!r.ok){
    showMsg('kbBackupMsg',r.error||'Backup failed','err');
    return;
  }
  showMsg('kbBackupMsg','Saved '+r.archive,'ok');
}
async function renderContent(){
  const cat=await api('/api/content/catalogue');
  const inst=await api('/api/content/installed');
  const browse=await api('/api/content/browse');
  const packs=cat.packs||[];
  const rows=packs.map(p=>{
    const st=p.installed?`<span class="pill-sm ok">installed ${escapeHtml(p.installed_version||'')}</span>`
      :`<span class="pill-sm bad">not installed</span>`;
    const btn=p.installed
      ?`<button class="btn secondary" onclick="uninstallPack('${escapeHtml(p.id)}')">Remove</button>`
      :`<button class="btn" onclick="installCataloguePack('${escapeHtml(p.id)}')">Install bundled</button>`;
    return `<tr>
      <td><strong>${escapeHtml(p.name||p.id)}</strong><br/><span style="color:var(--muted);font-size:.85rem">${escapeHtml(p.description||p.type||'')}</span></td>
      <td>${escapeHtml(p.version||'?')}</td>
      <td>${st}</td>
      <td>${btn}</td>
    </tr>`;
  }).join('');
  const local=(browse.local||[]).map(p=>
    `<div class="file-row" onclick="previewPack(decodeURIComponent('${jsQuote(p.path)}'))">
      <span>[pack] ${escapeHtml(p.name||p.id)}</span>
      <span class="meta">${escapeHtml(p.version||'')}</span>
    </div>`).join('');
  const usb=(browse.usb||[]).map(p=>
    `<div class="file-row" onclick="previewPack(decodeURIComponent('${jsQuote(p.path)}'))">
      <span>[usb] ${escapeHtml(p.name||p.id)}</span>
      <span class="meta">${escapeHtml(p.version||'')}</span>
    </div>`).join('');
  view.innerHTML=`<h1>Content packs</h1>
    <p style="margin-top:0">Install offline maps, knowledge, and model packs. Licences are shown before install.</p>
    <div class="card">
      <h3>Catalogue</h3>
      <table style="width:100%;border-collapse:collapse" cellpadding="8">
        <thead><tr><th align=left>Pack</th><th>Version</th><th>Status</th><th></th></tr></thead>
        <tbody>${rows||'<tr><td colspan=4>No catalogue entries.</td></tr>'}</tbody>
      </table>
    </div>
    <div class="grid-2">
      <div>
        <h2 style="font-size:1rem">Local / bundled packs</h2>
        <div class="file-browser">${local||'<div class="msg info" style="margin:.5rem">No .atlas-pack files found locally.</div>'}</div>
      </div>
      <div>
        <h2 style="font-size:1rem">USB import</h2>
        <div class="file-browser">${usb||'<div class="msg info" style="margin:.5rem">No USB packs detected. Plug in a drive with .atlas-pack files.</div>'}</div>
      </div>
    </div>
    <div id=contentPreview class="card" style="margin-top:1rem;display:none"></div>
    <div id=contentMsg style="margin-top:.75rem"></div>
    <h2 style="font-size:1rem;margin-top:1.25rem">Installed</h2>
    <div class="card">${(inst.packs||[]).map(p=>
      `<div class="stat-row"><span>${escapeHtml(p.name||p.id)}</span><span>${escapeHtml(p.version||'')}</span></div>`).join('')||'<p class="msg info">No packs installed yet.</p>'}</div>`;
}
async function previewPack(path){
  const r=await api('/api/content/preview?path='+encodeURIComponent(path));
  const box=document.getElementById('contentPreview');
  if(!box) return;
  if(r.error){
    box.style.display='block';
    box.innerHTML=`<div class="msg err">${escapeHtml(r.error)}</div>`;
    return;
  }
  const m=r.manifest||{};
  const lic=(r.licences||[]).map(l=>`<details><summary>${escapeHtml(l.name)}</summary><pre style="white-space:pre-wrap;font-size:.8rem">${escapeHtml(l.text)}</pre></details>`).join('');
  const compat=r.compat||{};
  const compatLine=compat.ok
    ?'<p style="color:var(--accent)">Compatible with this device.</p>'
    :`<p class="msg err">${escapeHtml((compat.errors||[]).join('; '))}</p>`;
  box.style.display='block';
  box.innerHTML=`<h3>${escapeHtml(m.name||m.id)}</h3>
    <p>${escapeHtml(m.description||'')}</p>
    <p style="font-size:.85rem;color:var(--muted)">Type: ${escapeHtml(m.type||'')} · Size ~${Math.round((m.size_bytes||0)/(1024*1024))} MB</p>
    ${compatLine}
    ${lic}
    <button class="btn" style="margin-top:.75rem" onclick="installPackPath(decodeURIComponent('${jsQuote(path)}'))">Install pack</button>`;
}
async function installPackPath(path){
  showMsg('contentMsg','Installing…','info');
  const r=await api('/api/content/install',{method:'POST',body:JSON.stringify({path})});
  if(r.error||!r.ok){
    showMsg('contentMsg',r.error||'Install failed','err');
    return;
  }
  showMsg('contentMsg','Installed '+r.name+' to '+r.target,'ok');
  renderContent();
}
async function installCataloguePack(id){
  showMsg('contentMsg','Installing bundled pack…','info');
  const r=await api('/api/content/install',{method:'POST',body:JSON.stringify({catalogue_id:id})});
  if(r.error||!r.ok){
    showMsg('contentMsg',r.error||'Install failed','err');
    return;
  }
  showMsg('contentMsg','Installed '+r.name,'ok');
  renderContent();
}
async function uninstallPack(id){
  if(!confirm('Remove pack '+id+'?')) return;
  const r=await api('/api/content/uninstall',{method:'POST',body:JSON.stringify({id})});
  if(r.error||!r.ok){
    showMsg('contentMsg',r.error||'Remove failed','err');
    return;
  }
  showMsg('contentMsg','Removed '+id,'ok');
  renderContent();
}
async function ask(){
  const qEl=document.getElementById('q');
  const sendBtn=document.getElementById('sendBtn');
  const text=(qEl&&qEl.value||'').trim();
  if(!text) return;
  const agent=(document.getElementById('agent')||{}).value||'atlas.guide';
  qEl.value='';
  _chatHistory.push({role:'user',content:text});
  renderChatLog(_chatHistory,true);
  if(sendBtn){sendBtn.disabled=true;sendBtn.textContent='Thinking…';}
  const r=await api('/api/ask',{method:'POST',body:JSON.stringify({
    prompt:text,agent,history:_chatHistory.slice(0,-1)
  })});
  if(sendBtn){sendBtn.disabled=false;sendBtn.textContent='Send';}
  const out=document.getElementById('out');
  if(out) out.textContent=JSON.stringify(r,null,2);
  const res=r.result||{};
  if(r.state==='awaiting_approval'||res.pending_approval){
    _chatHistory.push({role:'assistant',content:
      'This action needs your approval (e.g. fetching a web URL). Use Approve below, then ask again.'});
    renderChatLog(_chatHistory);
    refreshApprovals();
    return;
  }
  if(res.error||res.detail){
    const msg=[res.hint,res.detail,res.error].filter(Boolean).filter((v,i,a)=>a.indexOf(v)===i).join(' — ')
      ||'Something went wrong.';
    _chatHistory.push({role:'assistant',content:msg,isErr:true});
    renderChatLog(_chatHistory);
    return;
  }
  const answer=res.answer||'(No reply — check Models page or try again.)';
  const sources=res.sources||[];
  _chatHistory.push({role:'assistant',content:answer,sources});
  renderChatLog(_chatHistory);
  refreshApprovals();
}
function renderChatLog(msgs,thinking){
  const log=document.getElementById('chatLog');
  if(!log) return;
  let html=(msgs||[]).map(m=>{
    const cls=m.isErr?'err':(m.role==='user'?'user':'assistant');
    let body=`<div class="bubble ${cls}">${escapeHtml(m.content)}</div>`;
    if(m.sources&&m.sources.length){
      const cites=m.sources.slice(0,5).map(s=>{
        const label=escapeHtml(s.name||s.path||s.doc_id||'source');
        const doc=jsQuote(s.doc_id||'');
        const idx=Number(s.chunk_index||0);
        return `<a class="cite-link" onclick="openSource(decodeURIComponent('${doc}'),${idx})">${label}</a>`;
      }).join(' · ');
      body+=`<div class="cite-box"><strong>Sources</strong> ${cites}</div>`;
    }
    return body;
  }).join('');
  if(thinking) html+=`<div class="bubble system"><span class="spinner"></span> Thinking…</div>`;
  if(!html) html='<div class="bubble system">Say hello — Atlas Guide runs on your local model.</div>';
  log.innerHTML=html;
  log.scrollTop=log.scrollHeight;
}
async function openSource(docId,chunkIndex){
  location.hash='#/knowledge';
  setTimeout(async()=>{
    const r=await api('/api/knowledge/chunk?doc_id='+encodeURIComponent(docId)+'&chunk_index='+chunkIndex);
    const el=document.getElementById('kbSourceViewer');
    if(!el) return;
    if(r.error||!r.text){el.textContent=r.error||'Passage not found.';return;}
    el.innerHTML=`<strong>${escapeHtml(r.name||r.path||'')}</strong> · chunk ${r.chunk_index+1}/${r.total_chunks}\n\n${escapeHtml(r.text)}`;
  },80);
}
async function renderModels(){
  const m=await api('/api/models/status');
  const hw=m.hardware||{};
  const rec=m.recommended;
  const recBanner=rec?`<div style="border:1px solid var(--accent);padding:1rem;margin:1rem 0">
    <h2 style="margin-top:0">Recommended for this PC</h2>
    <p><strong>${rec.title}</strong> — ${rec.blurb}</p>
    <p>Size ~${rec.size_gb} GB · tag <code>${rec.tag}</code>
      ${rec.installed?'· <span style="color:var(--accent)">Installed</span>':''}</p>
    ${rec.installed?'':`<button class="btn dl-btn" data-tag="${rec.tag}" onclick="pullModel('${rec.tag}',this)">Download recommended</button>`}
    <p style="font-size:.9rem">Needs internet once. Afterwards Atlas stays offline.</p>
  </div>`:'<p>No compatible beginner model for this hardware.</p>';
  const rows=(m.catalogue||[]).map(c=>{
    const status=c.installed?'Installed':(c.compatible?'Available':'Not suitable');
    const btn=(!c.installed&&c.compatible)
      ?`<button class="btn dl-btn" data-tag="${c.tag}" onclick="pullModel('${c.tag}',this)">Download</button>`
      :(c.compatible?'':`<span style="color:#c97858">${(c.blockers||[]).join('; ')}</span>`);
    return `<tr>
      <td><strong>${c.title}</strong><br/><span style="color:var(--muted)">${c.blurb}</span></td>
      <td>~${c.size_gb} GB</td>
      <td>${status}</td>
      <td>${btn}</td>
    </tr>`;
  }).join('');
  view.innerHTML=`<h1>AI models</h1>
    <p>Atlas checked this machine: <strong>${hw.ram_gb||'?'} GB RAM</strong>,
      GPU <strong>${hw.gpu||'none'}</strong>,
      profile <strong>${m.profile||'?'}</strong>.
      Ollama: <strong>${m.ollama_reachable?'running':'not running'}</strong>.</p>
    ${m.gpu_warning?`<p style="color:#ffb4b4">${m.gpu_warning}</p>`:''}
    ${!m.ollama_reachable?'<p style="color:#ffb4b4">Start Ollama first: <code>sudo systemctl start ollama</code></p>':''}
    <div class="download-panel" id=downloadPanel>
      <h2>Download progress</h2>
      <div id=pullJobs><p class="download-msg">No download in progress.</p></div>
    </div>
    ${recBanner}
    ${(()=>{
      const emb=(m.catalogue||[]).find(c=>c.kind==='embed');
      if(!emb) return '';
      if(emb.installed||m.embed_ready) return `<p style="color:var(--accent)">Knowledge embeddings ready (${emb.tag}).</p>`;
      return `<div style="border:1px solid #c97858;padding:1rem;margin:1rem 0">
        <h2 style="margin-top:0">Knowledge embeddings</h2>
        <p>Semantic document search needs <strong>${emb.title}</strong> (${emb.tag}).</p>
        <button class="btn dl-btn" data-tag="${emb.tag}" onclick="pullModel('${emb.tag}',this)">Download embeddings model</button>
      </div>`;
    })()}
    <h2>All options</h2>
    <table style="width:100%;border-collapse:collapse" cellpadding="8">
      <thead><tr><th align=left>Model</th><th>Size</th><th>Status</th><th></th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <button class="btn secondary" onclick="renderModels()">Refresh list</button>`;
  setPullJobs(m.pull_jobs||[]);
  const running=(m.pull_jobs||[]).some(j=>j.status==='queued'||j.status==='running');
  if(running) pollPulls();
  else if(_pullTimer){clearInterval(_pullTimer);_pullTimer=null;}
}
let _pullTimer=null;
let _activePullJobs=[];
let _pullRefreshPending=false;
function onModelsHash(){
  return (location.hash.replace('#/','')||'home')==='models';
}
function setPullJobs(jobs){
  _activePullJobs=(jobs||[]).slice();
  renderPullUI();
}
function renderPullUI(){
  const box=document.getElementById('pullJobs');
  if(!box) return;
  if(!_activePullJobs.length){
    box.innerHTML='<p class="download-msg">No download in progress.</p>';
    return;
  }
  box.innerHTML=_activePullJobs.map(j=>{
    const pct=Math.max(0,Math.min(100,j.progress||0));
    const indeterminate=(j.status==='queued'||j.status==='running')&&pct===0;
    const bar=indeterminate
      ?'<div class="progress-track"><div class="progress-fill" style="width:40%;animation:pulse 1.2s ease-in-out infinite alternate"></div></div>'
      :`<div class="progress-track"><div class="progress-fill" style="width:${pct}%"></div></div>`;
    const cls=j.status==='failed'?'err':(j.status==='completed'?'ok':'');
    const spin=(j.status==='queued'||j.status==='running')?'<span class="spinner"></span>':'';
    return `<div class="download-row" data-job="${j.id||''}">
      <div class="label"><span>${spin}<strong>${j.tag||'model'}</strong></span>
        <span>${j.status||'?'}${pct?` · ${pct}%`:''}</span></div>
      ${bar}
      <div class="download-msg ${cls}">${j.message||''}</div>
    </div>`;
  }).join('');
  document.querySelectorAll('.dl-btn').forEach(b=>{
    const t=b.getAttribute('data-tag');
    const busy=_activePullJobs.some(j=>j.tag===t&&(j.status==='queued'||j.status==='running'));
    b.disabled=busy;
    if(busy) b.textContent='Downloading…';
  });
}
function disableDownloadButtons(tag,label){
  document.querySelectorAll('.dl-btn').forEach(b=>{
    if(!tag||b.getAttribute('data-tag')===tag){
      b.disabled=true;
      if(label) b.textContent=label;
    }
  });
}
async function pullModel(tag,btn){
  disableDownloadButtons(tag,'Starting…');
  setPullJobs([{tag,status:'queued',progress:0,message:'Contacting Ollama…'}]);
  const panel=document.getElementById('downloadPanel');
  if(panel) panel.scrollIntoView({behavior:'smooth',block:'nearest'});
  const r=await api('/api/models/pull',{method:'POST',body:JSON.stringify({tag})});
  if(r.error||r._status>=400){
    setPullJobs([{tag,status:'failed',progress:0,message:r.error||('HTTP '+r._status)}]);
    document.querySelectorAll('.dl-btn').forEach(b=>{b.disabled=false;if(b.getAttribute('data-tag')===tag)b.textContent='Download';});
    return;
  }
  if(r.id){
    setPullJobs([r]);
    pollPulls(true);
  }
}
async function pollPulls(immediate){
  if(_pullTimer){clearInterval(_pullTimer);_pullTimer=null;}
  async function tick(){
    if(!onModelsHash()){
      if(_pullTimer){clearInterval(_pullTimer);_pullTimer=null;}
      return;
    }
    const active=_activePullJobs.filter(j=>j.status==='queued'||j.status==='running');
    if(!active.length){
      if(_pullTimer){clearInterval(_pullTimer);_pullTimer=null;}
      return;
    }
    const ids=active.map(j=>j.id).filter(Boolean);
    if(!ids.length) return;
    let anyRunning=false;
    const updated=[];
    for(const id of ids){
      const s=await api('/api/models/pull/'+id);
      if(s.error) continue;
      updated.push(s);
      if(s.status==='queued'||s.status==='running') anyRunning=true;
    }
    if(updated.length){
      // Keep completed rows visible, replace matching ids
      const byId={};
      _activePullJobs.forEach(j=>{if(j.id) byId[j.id]=j;});
      updated.forEach(s=>{byId[s.id]=s;});
      setPullJobs(Object.values(byId));
    }
    if(!anyRunning){
      if(_pullTimer){clearInterval(_pullTimer);_pullTimer=null;}
      if(!_pullRefreshPending && onModelsHash()){
        _pullRefreshPending=true;
        setTimeout(()=>{
          _pullRefreshPending=false;
          if(onModelsHash()) renderModels();
        },800);
      }
    }
  }
  if(immediate) await tick();
  if(_activePullJobs.some(j=>j.status==='queued'||j.status==='running')){
    _pullTimer=setInterval(tick,1200);
  }
}
async function refreshApprovals(){
  const el=document.getElementById('approvals');
  const banner=document.getElementById('approvalBanner');
  if(!el&&!banner) return;
  try{
    const a=await api('/api/approvals');
    if(banner){
      if(!a.pending||!a.pending.length){banner.classList.remove('show');banner.innerHTML='';return;}
      banner.classList.add('show');
      banner.innerHTML=`<strong>Approval needed</strong>
        ${a.pending.map(p=>`<div style="margin-top:.5rem">${p.tool_id||'action'}
          <button class=btn onclick="decide('${p.approval_id}','${p.task_id||''}',true)">Approve</button>
          <button class="btn secondary" onclick="decide('${p.approval_id}','${p.task_id||''}',false)">Deny</button>
        </div>`).join('')}`;
      return;
    }
    if(!a.pending||!a.pending.length){if(el)el.textContent='None';return;}
    if(el) el.innerHTML=a.pending.map(p=>
      `<div>${p.approval_id} tool=${p.tool_id} task=${p.task_id||'?'}
        <button class=btn onclick="decide('${p.approval_id}','${p.task_id||''}',true)">Approve</button>
        <button class=btn onclick="decide('${p.approval_id}','${p.task_id||''}',false)">Deny</button>
      </div>`
    ).join('');
  }catch(e){if(el)el.textContent=String(e);}
}
async function decide(aid,tid,ok){
  const r=await api('/api/approvals/'+aid,{method:'POST',body:JSON.stringify({approve:ok,task_id:tid})});
  const out=document.getElementById('out');
  if(out) out.textContent=JSON.stringify(r,null,2);
  if(ok&&r.result&&r.result.answer){
    _chatHistory.push({role:'assistant',content:r.result.answer});
    renderChatLog(_chatHistory);
  }
  refreshApprovals();
}
async function createFullBackup(){
  const pass=(document.getElementById('bakPass')||{}).value||'';
  if(!pass){showMsg('bakMsg','Enter a passphrase.','err');return;}
  showMsg('bakMsg','Creating encrypted backup…','info');
  const r=await api('/api/backup/create',{method:'POST',body:JSON.stringify({passphrase:pass})});
  if(r.error||!r.ok){showMsg('bakMsg',r.error||'Backup failed','err');return;}
  showMsg('bakMsg','Saved '+r.path,'ok');
  page();
}
async function verifyBackup(path){
  const r=await api('/api/backup/verify',{method:'POST',body:JSON.stringify({path})});
  if(r.error||!r.ok){showMsg('bakMsg',r.error||'Verify failed','err');return;}
  showMsg('bakMsg','Backup verified.','ok');
}
async function restoreBackupPrompt(path){
  const pass=prompt('Passphrase for restore:');
  if(pass===null) return;
  if(!confirm('Restore will overwrite Atlas data on this device. Continue?')) return;
  showMsg('bakMsg','Restoring…','info');
  const r=await api('/api/backup/restore',{method:'POST',body:JSON.stringify({path,passphrase:pass})});
  if(r.error||!r.ok){showMsg('bakMsg',r.error||'Restore failed','err');return;}
  showMsg('bakMsg','Restored: '+(r.restored||[]).join(', '),'ok');
}
async function previewUpdate(path){
  const r=await api('/api/updates/preview?path='+encodeURIComponent(path));
  const box=document.getElementById('updPreview');
  if(!box) return;
  if(r.error){
    box.style.display='block';
    box.innerHTML=`<div class="msg err">${escapeHtml(r.error)}</div>`;
    return;
  }
  const m=r.manifest||{};
  box.style.display='block';
  box.innerHTML=`<h4>${escapeHtml(m.from_version||'?')} → ${escapeHtml(m.to_version||'?')}</h4>
    <p style="font-size:.85rem;color:var(--muted)">${escapeHtml(m.publisher||'')}</p>
    <pre style="white-space:pre-wrap;font-size:.85rem">${escapeHtml(r.release_notes||'No release notes.')}</pre>
    <button class="btn" onclick="applyUpdateBundle(decodeURIComponent('${jsQuote(path)}'))">Apply update</button>`;
}
async function applyUpdateBundle(path){
  if(!confirm('Apply this update? A snapshot will be taken first.')) return;
  showMsg('updMsg','Applying update…','info');
  const r=await api('/api/updates/apply',{method:'POST',body:JSON.stringify({path})});
  if(r.error==='bad_response'){
    showMsg('updMsg','Update failed (empty/invalid server response). Check atlas-command-centre logs.','err');
    return;
  }
  if(r.error||r.ok===false){
    showMsg('updMsg',(r.detail||r.error||'Update failed')+(r.rolled_back?' (rolled back)':''),'err');
    return;
  }
  showMsg('updMsg','Applied '+ (r.version||r.detail),'ok');
}
async function nextStep(){
  await api('/api/setup/advance',{method:'POST',body:'{}'});
  page();
}
async function reauth(){
  const r=await api('/api/auth/reauth',{method:'POST',body:JSON.stringify({password:rp.value})});
  const el=document.getElementById('reout');
  if(!el) return;
  if(r.ok) el.innerHTML='<div class="msg ok">Password confirmed.</div>';
  else el.innerHTML='<div class="msg err">Confirmation failed.</div>';
}
async function boot(){
  try{
    const ok=await ensureSession();
    if(ok) page();
  }catch(e){
    console.error(e);
    showGateError('Startup error: '+(e&&e.message?e.message:String(e)));
  }
}
const logoutLink=document.getElementById('logoutLink');
if(logoutLink) logoutLink.addEventListener('click',e=>{e.preventDefault();doLogout();});
window.addEventListener('hashchange',()=>{
  if(!onModelsHash() && _pullTimer){clearInterval(_pullTimer);_pullTimer=null;}
  if(authed) page();
});
boot();
</script></body></html>
"""


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
            prev = os.environ.get("ATLAS_ALLOW_UNSIGNED")
            os.environ["ATLAS_ALLOW_UNSIGNED"] = "1"
            try:
                result = apply_update(p, atlas_data=DATA, dry_run=False)
            except Exception as e:
                return self._json(500, {"error": str(e), "ok": False})
            finally:
                if prev is None:
                    os.environ.pop("ATLAS_ALLOW_UNSIGNED", None)
                else:
                    os.environ["ATLAS_ALLOW_UNSIGNED"] = prev
            audit_event({
                "event": "update.apply",
                "path": str(p),
                "ok": result.ok,
                "rolled_back": result.rolled_back,
                "version": result.version,
                "username": sess["username"],
            })
            # Always 200 with ok/rolled_back so the UI can parse JSON reliably
            body = result.to_dict()
            if not result.ok:
                body["error"] = result.detail
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

    def log_message(self, fmt, *args):  # noqa: A003
        sys.stderr.write("atlas-cc: " + (fmt % args) + "\n")


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "databases").mkdir(parents=True, exist_ok=True)
    (DATA / "logs").mkdir(parents=True, exist_ok=True)
    (DATA / "knowledge").mkdir(parents=True, exist_ok=True)
    (DATA / "backups" / "knowledge").mkdir(parents=True, exist_ok=True)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    UPDATE_INCOMING.mkdir(parents=True, exist_ok=True)
    (DATA / "snapshots").mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Atlas Command Centre on http://{HOST}:{PORT}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
