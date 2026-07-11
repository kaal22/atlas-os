#!/usr/bin/env python3
"""Atlas Command Centre — local API + UI on 127.0.0.1:8787."""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

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
    PACKAGES / "atlas-system-daemon" / "usr" / "lib" / "atlas",
    Path("/usr/lib/atlas"),
]
for c in LIB_CANDIDATES:
    if c.exists():
        sys.path.insert(0, str(c))

from auth_store import AuthStore  # noqa: E402
from policy_gateway import default_gateway  # noqa: E402
from agent_runtime import AgentRuntime, AgentManifest  # noqa: E402
from model_router import probe_hardware, recommend, recommendation_bundle  # noqa: E402
from knowledge_service import KnowledgeService  # noqa: E402

try:
    from gpu_detect import as_api_dict as gpu_as_api_dict
except ImportError:
    gpu_as_api_dict = None  # type: ignore

HOST = "127.0.0.1"
PORT = 8787
DATA = Path("/srv/atlas") if Path("/srv/atlas").exists() else Path("/tmp/atlas-dev")
AUTH = AuthStore(DATA / "databases" / "auth.json")
AUTH.load()
if not AUTH.users:
    AUTH.create_user("atlas", "atlas", "owner")  # first-run must force password change

GW = default_gateway()
RT = AgentRuntime(gateway=GW)
for agent_file in [
    Path("/usr/share/atlas/agents"),
    HERE.parents[1] / "share" / "atlas" / "agents",
    PACKAGES / "atlas-agent-runtime" / "usr" / "share" / "atlas" / "agents",
]:
    if agent_file.exists():
        for p in agent_file.glob("*.json"):
            RT.register_agent(AgentManifest.from_dict(json.loads(p.read_text(encoding="utf-8"))))
        break

KS = KnowledgeService(DATA / "knowledge")
WIZARD_STATE = DATA / "databases" / "first-run.json"


UI = """<!DOCTYPE html>
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
.pre{white-space:pre-wrap;background:#071525;padding:.75rem;font-family:ui-monospace,monospace;font-size:.85rem;color:var(--text)}
.hidden{display:none}
</style></head><body>
<header><div class="brand">Atlas <span>OS</span></div><nav>
<a href="#/ask">Ask</a><a href="#/agents">Agents</a><a href="#/knowledge">Knowledge</a>
<a href="#/system">System</a><a href="#/setup">Setup</a></nav></header>
<main>
<aside id="side"></aside>
<section id="view"></section>
</main>
<script>
const view=document.getElementById('view');
const side=document.getElementById('side');
let token=localStorage.getItem('atlasToken')||'';
async function api(path,opts={}){
  const headers=Object.assign({'Content-Type':'application/json'}, opts.headers||{});
  if(token) headers['Authorization']='Bearer '+token;
  const r=await fetch(path,{...opts,headers});
  return r.json();
}
function routes(){return [
  ['Home','home'],['Ask','ask'],['Agents','agents'],['Knowledge','knowledge'],
  ['System','system'],['Setup','setup'],['Login','login']
];}
function renderNav(active){
  side.innerHTML=routes().map(([l,id])=>`<button class="${active===id?'active':''}" onclick="location.hash='#/${id}'">${l}</button>`).join('');
}
async function page(){
  const id=(location.hash.replace('#/','')||'home');
  renderNav(id);
  if(id==='login'){
    view.innerHTML=`<h1>Sign in</h1><input id=u placeholder=username value=atlas /><input id=p type=password placeholder=password value=atlas />
      <button class=btn onclick="doLogin()">Login</button><p>Change the default password during Setup.</p>`;
    return;
  }
  if(id==='home'){
    const h=await api('/api/system/health');
    view.innerHTML=`<h1>Command Centre</h1><p>Private offline AI and knowledge environment.</p>
      <div class=pre>${JSON.stringify(h,null,2)}</div>`;
    return;
  }
  if(id==='ask'){
    view.innerHTML=`<h1>Ask Atlas Guide</h1><textarea id=q placeholder="Ask a local question..."></textarea>
      <button class=btn onclick="ask()">Send</button><div class=pre id=out></div>`;
    return;
  }
  if(id==='agents'){
    const a=await api('/api/agents');
    view.innerHTML=`<h1>Agents</h1><div class=pre>${JSON.stringify(a,null,2)}</div>`;
    return;
  }
  if(id==='knowledge'){
    view.innerHTML=`<h1>Knowledge</h1><p>Import a local text/markdown path on the server (dev).</p>
      <input id=path placeholder="/srv/atlas/documents/note.md" />
      <button class=btn onclick="ingest()">Ingest</button>
      <input id=sq placeholder="search query" />
      <button class=btn onclick="search()">Search</button><div class=pre id=out></div>`;
    return;
  }
  if(id==='system'){
    const hw=await api('/api/models/recommend');
    const gpu=await api('/api/system/gpu');
    const warn=hw.warning?`<p style="color:#ffb4b4">${hw.warning}</p>
      <p><code>${hw.install_command||'sudo atlas-gpu-setup --install-nvidia'}</code></p>`:'';
    view.innerHTML=`<h1>System</h1>${warn}<h2>AI profile</h2><div class=pre>${JSON.stringify(hw,null,2)}</div>
      <h2>GPU</h2><div class=pre>${JSON.stringify(gpu,null,2)}</div>
      <p>Offline guide: <code>/usr/share/atlas/docs/GPU_SETUP.md</code></p>`;
    return;
  }
  if(id==='setup'){
    const st=await api('/api/setup/state');
    view.innerHTML=`<h1>First-run setup</h1><div class=pre>${JSON.stringify(st,null,2)}</div>
      <button class=btn onclick="nextStep()">Advance step</button>`;
  }
}
async function doLogin(){
  const r=await api('/api/auth/login',{method:'POST',body:JSON.stringify({username:u.value,password:p.value})});
  if(r.token){token=r.token;localStorage.setItem('atlasToken',token);location.hash='#/home';}
  else alert(r.error||'login failed');
}
async function ask(){
  const r=await api('/api/ask',{method:'POST',body:JSON.stringify({prompt:q.value,agent:'atlas.guide'})});
  out.textContent=JSON.stringify(r,null,2);
}
async function ingest(){
  const r=await api('/api/knowledge/ingest',{method:'POST',body:JSON.stringify({path:path.value})});
  out.textContent=JSON.stringify(r,null,2);
}
async function search(){
  const r=await api('/api/knowledge/search',{method:'POST',body:JSON.stringify({query:sq.value})});
  out.textContent=JSON.stringify(r,null,2);
}
async function nextStep(){
  await api('/api/setup/advance',{method:'POST',body:'{}'});
  page();
}
window.addEventListener('hashchange',page);page();
</script></body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, obj) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth(self):
        hdr = self.headers.get("Authorization", "")
        if not hdr.startswith("Bearer "):
            return None
        try:
            return AUTH.require(hdr[7:])
        except PermissionError:
            return None

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
        if path == "/api/system/health":
            health = {"status": "ok", "bind": f"{HOST}:{PORT}", "services": {"command_centre": True}}
            try:
                bundle = recommendation_bundle()
                if bundle.get("warning"):
                    health["status"] = "degraded"
                    health["gpu_warning"] = bundle["warning"]
            except Exception:
                pass
            return self._json(200, health)
        if path == "/api/agents":
            return self._json(200, {"agents": [a.__dict__ for a in RT.agents.values()]})
        if path == "/api/models/recommend":
            try:
                return self._json(200, recommendation_bundle())
            except Exception:
                hw = probe_hardware()
                return self._json(200, {"ram_gb": hw.ram_gb, "vram_gb": hw.vram_gb, "profile": recommend(hw)})
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
        self._json(404, {"error": "not_found"})

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            return self._json(400, {"error": "bad_json"})

        if path == "/api/auth/login":
            try:
                tok = AUTH.login(data["username"], data["password"])
                return self._json(200, {"token": tok})
            except Exception as e:
                return self._json(401, {"error": str(e)})

        sess = self._auth()
        if path != "/api/auth/login" and sess is None and path.startswith("/api/"):
            # Allow health without auth already handled; protect the rest
            if path not in {"/api/auth/login"}:
                return self._json(401, {"error": "unauthorized"})

        if path == "/api/ask":
            agent = data.get("agent", "atlas.guide")
            task = RT.create_task(agent, data.get("prompt", ""))
            RT.plan(task.id)
            result = RT.run_step(task.id)
            return self._json(200, {"task_id": task.id, "state": task.state, "result": result})

        if path == "/api/knowledge/ingest":
            p = Path(data["path"])
            if not p.exists():
                return self._json(404, {"error": "file_not_found"})
            rec = KS.ingest_file(sess["username"], p)
            return self._json(200, {"doc_id": rec.doc_id, "chunks": len(rec.chunks)})

        if path == "/api/knowledge/search":
            hits = KS.search(sess["username"], data.get("query", ""))
            return self._json(200, {"hits": hits})

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

        self._json(404, {"error": "not_found"})

    def log_message(self, fmt, *args):  # noqa: A003
        sys.stderr.write("atlas-cc: " + (fmt % args) + "\n")


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "databases").mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Atlas Command Centre on http://{HOST}:{PORT}/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
