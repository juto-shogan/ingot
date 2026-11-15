#!/usr/bin/env python3
"""
Ingot local web UI.

Paste a GitHub URL or a local folder path, click Extract, and copy or download
the bundled text. Runs only on your own machine (127.0.0.1), standard library only.
"""

import json
import os
import re
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import ingot

LOCK = threading.Lock()
MAX_BODY = 1024 * 1024


def split_csv(text):
    return [p.strip() for p in (text or "").replace("\n", ",").split(",") if p.strip()]


def list_history(out_dir, limit=40):
    items = []
    if out_dir.is_dir():
        for p in out_dir.rglob("*.txt"):
            try:
                st = p.stat()
            except OSError:
                continue
            project = p.parent.name if p.parent != out_dir else p.stem
            items.append({"path": p.relative_to(out_dir).as_posix(), "project": project,
                          "size": st.st_size, "mtime": st.st_mtime})
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items[:limit]


def make_handler(store, out_dir, port):
    allowed_hosts = {"127.0.0.1:{}".format(port), "localhost:{}".format(port)}

    class Handler(BaseHTTPRequestHandler):
        server_version = "Ingot"

        def log_message(self, fmt, *args):
            pass

        # -- helpers ---------------------------------------------------------
        def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, obj):
            self._send(code, json.dumps(obj))

        def _guard(self):
            """Block other websites and DNS-rebinding tricks from using this server."""
            if self.headers.get("Host", "") not in allowed_hosts:
                self._json(403, {"ok": False, "error": "Forbidden host."})
                return False
            origin = self.headers.get("Origin")
            if origin and origin.split("://", 1)[-1] not in allowed_hosts:
                self._json(403, {"ok": False, "error": "Forbidden origin."})
                return False
            return True

        def _state(self):
            return {"saved": store["items"], "history": list_history(out_dir),
                    "output_dir": str(out_dir), "has_token": bool(os.environ.get("GITHUB_TOKEN"))}

        def _safe_file(self, rel):
            try:
                p = (out_dir / rel).resolve()
                p.relative_to(out_dir)
            except (ValueError, OSError):
                return None
            return p if p.is_file() and p.suffix == ".txt" else None

        # -- GET ---------------------------------------------------------------
        def do_GET(self):
            if not self._guard():
                return
            url = urlparse(self.path)
            qs = parse_qs(url.query)
            if url.path == "/":
                self._send(200, PAGE, "text/html; charset=utf-8")
            elif url.path == "/api/state":
                self._json(200, self._state())
            elif url.path == "/api/repos":
                user = qs.get("user", [""])[0]
                if not re.match(r"^[\w.-]+$", user):
                    self._json(400, {"ok": False, "error": "Bad username."})
                    return
                try:
                    repos = ingot.list_account_repos(user, os.environ.get("GITHUB_TOKEN"))
                except ingot.IngotError as e:
                    self._json(200, {"ok": False, "error": str(e)})
                    return
                self._json(200, {"ok": True, "repos": [
                    {"full_name": r["full_name"], "description": r.get("description") or ""} for r in repos]})
            elif url.path in ("/api/file", "/download"):
                rel = qs.get("path", [""])[0]
                target = self._safe_file(rel)
                if not target:
                    self._json(404, {"ok": False, "error": "File not found."})
                    return
                text = target.read_text(encoding="utf-8", errors="replace")
                if url.path == "/download":
                    self._send(200, text, "text/plain; charset=utf-8",
                               {"Content-Disposition": 'attachment; filename="{}"'.format(target.name)})
                else:
                    self._json(200, {"ok": True, "text": text, "path": rel,
                                     "project": target.parent.name})
            else:
                self._json(404, {"ok": False, "error": "Not found."})

        # -- POST --------------------------------------------------------------
        def do_POST(self):
            if not self._guard():
                return
            if "application/json" not in self.headers.get("Content-Type", ""):
                self._json(415, {"ok": False, "error": "JSON required."})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                length = 0
            if length > MAX_BODY:
                self._json(413, {"ok": False, "error": "Request too large."})
                return
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._json(400, {"ok": False, "error": "Bad JSON."})
                return
            path = urlparse(self.path).path
            if path == "/api/extract":
                self._extract(body)
            elif path == "/api/save":
                self._save(body)
            elif path == "/api/remove":
                item = ingot.find_saved(store, body.get("name", ""))
                if item:
                    store["items"].remove(item)
                    ingot.save_store(store)
                self._json(200, {"ok": True, "saved": store["items"]})
            else:
                self._json(404, {"ok": False, "error": "Not found."})

        def _save(self, b):
            kind = b.get("kind")
            name = (b.get("name") or "").strip()
            target = (b.get("target") or "").strip()
            if kind not in ("github", "account", "local") or not name or not target:
                self._json(400, {"ok": False, "error": "Name, type and target are required."})
                return
            if kind == "local":
                target = str(Path(target).expanduser().resolve())
            ingot.add_saved(store, name, kind, target, (b.get("branch") or None))
            self._json(200, {"ok": True, "saved": store["items"]})

        def _extract(self, b):
            kind = b.get("kind")
            target = (b.get("target") or "").strip().strip('"').strip("'")
            if kind not in ("github", "local") or not target:
                self._json(400, {"ok": False, "error": "Enter a GitHub repo or a folder path."})
                return
            logs = []
            opts = ingot.base_opts(store)
            opts.update({
                "output_dir": str(out_dir),
                "branch": (b.get("branch") or "").strip() or None,
                "excludes": split_csv(b.get("exclude")),
                "exts": split_csv(b.get("ext")),
                "use_gitignore": bool(b.get("use_gitignore", True)),
                "nb_outputs": bool(b.get("nb_outputs")),
                "log": logs.append,
            })
            try:
                mk = int(b.get("max_kb") or 0)
                if mk > 0:
                    opts["max_kb"] = mk
            except (TypeError, ValueError):
                pass
            with LOCK:
                try:
                    res = ingot.run_job(kind, target, opts)
                except ingot.IngotError as e:
                    self._json(200, {"ok": False, "error": str(e), "log": logs})
                    return
                except Exception as e:  # keep the server alive on unexpected errors
                    self._json(500, {"ok": False, "error": "Unexpected error: {}".format(e), "log": logs})
                    return
            nick = (b.get("save_as") or "").strip()
            if nick:
                saved_target = target if kind == "github" else str(Path(target).expanduser().resolve())
                ingot.add_saved(store, nick, kind, saved_target, opts["branch"])
            path = res["path"].resolve()
            self._json(200, {
                "ok": True, "project": res["project"], "files": res["files"], "lines": res["lines"],
                "tokens": res["tokens"], "skipped": res["skipped"],
                "path": path.relative_to(out_dir).as_posix(), "abs_path": str(path),
                "text": res["text"], "log": logs, "saved": store["items"],
            })

    return Handler


def serve(store, port=8765, open_browser=True):
    out_dir = Path(store["settings"]["output_dir"]).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    server = None
    for p in range(port, port + 11):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", p), make_handler(store, out_dir, p))
            port = p
            break
        except OSError:
            continue
    if server is None:
        print("Error: could not open a port near {}. Try --port.".format(port))
        return
    url = "http://127.0.0.1:{}".format(port)
    print("Ingot web UI running at {}   (Ctrl+C to stop)".format(url))
    print("Bundles are saved in: {}".format(out_dir))
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


PAGE = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ingot</title>
<style>
:root{--bg:#f6f5f2;--card:#fff;--text:#1d1d1b;--muted:#6b6a65;--line:#e2e0da;--accent:#c2410c;--accent-fg:#fff;--ok:#15803d;--err:#b91c1c;--field:#faf9f7}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--card:#1f1f1d;--text:#ececea;--muted:#9b9a94;--line:#33322e;--accent:#fb923c;--accent-fg:#1a1208;--ok:#4ade80;--err:#f87171;--field:#171716}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
header{max-width:1100px;margin:0 auto;padding:28px 20px 8px}
header h1{margin:0;font-size:26px;letter-spacing:-.02em}
header p{margin:2px 0 0;color:var(--muted)}
main{max-width:1100px;margin:0 auto;padding:16px 20px 48px;display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:18px}
@media (max-width:860px){main{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin-bottom:18px}
.card h2{margin:0 0 10px;font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.seg{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden;margin-bottom:14px}
.seg button{border:0;background:transparent;color:var(--muted);padding:7px 16px;font:inherit;cursor:pointer}
.seg button.on{background:var(--accent);color:var(--accent-fg)}
label{display:block;font-size:13px;color:var(--muted);margin:10px 0 4px}
input[type=text],input[type=number],textarea{width:100%;padding:9px 11px;border:1px solid var(--line);border-radius:8px;background:var(--field);color:var(--text);font:inherit}
input:focus,textarea:focus{outline:2px solid var(--accent);outline-offset:-1px}
details{margin-top:12px}summary{cursor:pointer;color:var(--muted);font-size:13px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.chk{display:flex;gap:8px;align-items:center;margin-top:10px;font-size:14px;color:var(--text)}
.row{display:flex;gap:10px;margin-top:14px;align-items:center}
.row input{flex:1}
button.primary{background:var(--accent);color:var(--accent-fg);border:0;border-radius:8px;padding:9px 20px;font:inherit;font-weight:600;cursor:pointer}
button.primary:disabled{opacity:.55;cursor:wait}
button.ghost{background:transparent;color:var(--text);border:1px solid var(--line);border-radius:8px;padding:6px 12px;font:inherit;cursor:pointer;text-decoration:none;display:inline-block;font-size:14px}
button.ghost:hover{border-color:var(--accent)}
#status{margin-top:10px;font-size:14px;min-height:20px}
.ok{color:var(--ok)}.err{color:var(--err)}.muted{color:var(--muted)}
.stats{display:flex;gap:18px;flex-wrap:wrap;margin:2px 0 8px;font-size:14px}
.stats b{font-size:18px;display:block}
.path{font:12px ui-monospace,Consolas,monospace;color:var(--muted);word-break:break-all;margin-bottom:10px}
.bar{display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap}
textarea#out{height:420px;font:12px/1.45 ui-monospace,Consolas,monospace;white-space:pre;resize:vertical}
.grp{display:flex;align-items:center;justify-content:space-between;margin:10px 0 4px;font-weight:600;font-size:14px}
.item{display:flex;align-items:center;gap:6px;margin:2px 0}
.item button.pick{flex:1;text-align:left;background:transparent;border:0;color:var(--text);padding:5px 8px;border-radius:6px;font:inherit;font-size:14px;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.item button.pick:hover{background:var(--field)}
.item button.x{background:transparent;border:0;color:var(--muted);cursor:pointer;font-size:16px}
.item button.x:hover{color:var(--err)}
.small{font-size:12px;color:var(--muted)}
.link{background:none;border:0;color:var(--accent);cursor:pointer;font:inherit;font-size:12px;padding:0}
</style>
</head>
<body>
<header>
  <h1>Ingot</h1>
  <p>Melt a codebase into one AI-ready text file.</p>
</header>
<main>
  <section>
    <div class="card">
      <div class="seg"><button id="tabGh" class="on">GitHub</button><button id="tabLocal">Local folder</button></div>
      <label id="targetLabel" for="target">GitHub repo URL or owner/repo</label>
      <input id="target" type="text" placeholder="https://github.com/owner/repo" autocomplete="off" spellcheck="false">
      <div id="branchRow"><label for="branch">Branch or tag (optional)</label><input id="branch" type="text" placeholder="default branch"></div>
      <details>
        <summary>Options</summary>
        <div class="two">
          <div><label for="ext">Only these extensions</label><input id="ext" type="text" placeholder="py, js, md"></div>
          <div><label for="exclude">Skip patterns</label><input id="exclude" type="text" placeholder="tests/*, *.min.css"></div>
          <div><label for="maxkb">Max file size (KB)</label><input id="maxkb" type="number" min="1" placeholder="500"></div>
        </div>
        <label class="chk"><input type="checkbox" id="gitignore" checked> Respect the project's .gitignore</label>
        <label class="chk"><input type="checkbox" id="nbout"> Include Jupyter notebook cell outputs</label>
      </details>
      <div class="row">
        <input id="saveAs" type="text" placeholder="Save as shortcut (optional nickname)" autocomplete="off">
        <button id="go" class="primary">Extract</button>
      </div>
      <div id="status"></div>
    </div>

    <div class="card" id="result" hidden>
      <h2>Result</h2>
      <div class="stats" id="stats"></div>
      <div class="path" id="where"></div>
      <div class="bar">
        <button class="ghost" id="copy">Copy all text</button>
        <a class="ghost" id="dl" href="#">Download .txt</a>
      </div>
      <textarea id="out" readonly spellcheck="false"></textarea>
    </div>
  </section>

  <aside>
    <div class="card"><h2>Saved</h2><div id="saved"></div></div>
    <div class="card"><h2>Recent bundles</h2><div id="history"></div><div class="small" id="outdir" style="margin-top:8px"></div></div>
  </aside>
</main>
<script>
const $ = s => document.querySelector(s);
let kind = 'github', current = null;

function el(tag, props, ...kids){ const e = document.createElement(tag); Object.assign(e, props || {}); kids.forEach(k => e.append(k)); return e; }

async function api(path, body){
  const r = await fetch(path, body ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {});
  return r.json();
}

function setKind(k){
  kind = k;
  $('#tabGh').classList.toggle('on', k === 'github');
  $('#tabLocal').classList.toggle('on', k === 'local');
  $('#branchRow').style.display = k === 'github' ? '' : 'none';
  $('#targetLabel').textContent = k === 'github' ? 'GitHub repo URL or owner/repo' : 'Full path to a folder on this computer';
  $('#target').placeholder = k === 'github' ? 'https://github.com/owner/repo' : 'C:\\Users\\you\\projects\\my-app';
}
$('#tabGh').onclick = () => setKind('github');
$('#tabLocal').onclick = () => setKind('local');

function status(msg, cls){ const s = $('#status'); s.textContent = msg; s.className = cls || 'muted'; }

function fmtSize(n){ return n > 1048576 ? (n/1048576).toFixed(1) + ' MB' : Math.max(1, Math.round(n/1024)) + ' KB'; }

function showResult(r){
  current = r;
  $('#result').hidden = false;
  const s = $('#stats'); s.replaceChildren();
  if (r.files !== undefined){
    [['Files', r.files], ['Lines', r.lines.toLocaleString()], ['~Tokens', r.tokens.toLocaleString()]].forEach(([k, v]) =>
      s.append(el('div', {}, el('b', {textContent: String(v)}), k)));
  } else {
    s.append(el('div', {}, el('b', {textContent: r.project}), 'Loaded from history'));
  }
  $('#where').textContent = r.abs_path || r.path;
  $('#out').value = r.text;
  $('#dl').href = '/download?path=' + encodeURIComponent(r.path);
  $('#result').scrollIntoView({behavior:'smooth', block:'start'});
}

$('#copy').onclick = async () => {
  if (!current) return;
  try { await navigator.clipboard.writeText(current.text); }
  catch (e) { $('#out').select(); document.execCommand('copy'); }
  const b = $('#copy'); const old = b.textContent; b.textContent = 'Copied!';
  setTimeout(() => b.textContent = old, 1400);
};

function pick(i){
  if (i.type === 'local'){ setKind('local'); $('#target').value = i.target; $('#branch').value = ''; }
  else { setKind('github'); $('#target').value = i.target; $('#branch').value = i.branch || ''; }
  $('#target').focus();
}

function savedRow(i){
  return el('div', {className:'item'},
    el('button', {className:'pick', textContent:i.name, title:i.target, onclick:() => pick(i)}),
    el('button', {className:'x', textContent:'\u00d7', title:'Remove', onclick: async () => {
      const r = await api('/api/remove', {name:i.name}); renderSaved(r.saved); }}));
}

function renderSaved(items){
  const box = $('#saved'); box.replaceChildren();
  if (!items.length){ box.append(el('p', {className:'muted', textContent:'Nothing saved yet. Add a nickname when you extract.'})); return; }
  const accounts = [...new Set(items.filter(i => i.account).map(i => i.account))];
  accounts.forEach(a => {
    const repoBox = el('div', {});
    const head = el('div', {className:'grp'}, el('span', {textContent:'@' + a}),
      el('button', {className:'link', textContent:'browse repos', onclick: async () => {
        repoBox.replaceChildren(el('div', {className:'small', textContent:'Loading...'}));
        const r = await api('/api/repos?user=' + encodeURIComponent(a));
        repoBox.replaceChildren();
        if (!r.ok){ repoBox.append(el('div', {className:'small err', textContent:r.error})); return; }
        r.repos.slice(0, 40).forEach(x => repoBox.append(el('div', {className:'item'},
          el('button', {className:'pick', textContent:x.full_name, title:x.description,
            onclick:() => pick({type:'github', target:x.full_name})}))));
      }}));
    box.append(head);
    items.filter(i => i.type === 'github' && i.account === a).forEach(i => box.append(savedRow(i)));
    items.filter(i => i.type === 'account' && i.account === a).forEach(i => {
      if (!items.some(j => j.type === 'github' && j.account === a)) box.append(el('div', {className:'small', textContent:'Account saved - use browse repos'}));
    });
    box.append(repoBox);
  });
  const locals = items.filter(i => i.type === 'local');
  if (locals.length){ box.append(el('div', {className:'grp', textContent:'Local folders'})); locals.forEach(i => box.append(savedRow(i))); }
}

function renderHistory(items, dir){
  const box = $('#history'); box.replaceChildren();
  if (!items.length) box.append(el('p', {className:'muted', textContent:'No bundles yet.'}));
  items.slice(0, 12).forEach(h => box.append(el('div', {className:'item'},
    el('button', {className:'pick', title:h.path, textContent:h.project + '  -  ' + fmtSize(h.size) + '  -  ' + new Date(h.mtime * 1000).toLocaleDateString(),
      onclick: async () => { const r = await api('/api/file?path=' + encodeURIComponent(h.path)); if (r.ok) showResult(r); }}))));
  if (dir) $('#outdir').textContent = 'Folder: ' + dir;
}

$('#go').onclick = async () => {
  const target = $('#target').value.trim();
  if (!target){ status('Enter a ' + (kind === 'github' ? 'GitHub repo' : 'folder path') + ' first.', 'err'); return; }
  const btn = $('#go'); btn.disabled = true;
  status(kind === 'github' ? 'Cloning and bundling... this can take a bit for big repos.' : 'Bundling...', 'muted');
  try {
    const r = await api('/api/extract', {
      kind, target, branch:$('#branch').value, ext:$('#ext').value, exclude:$('#exclude').value,
      max_kb:$('#maxkb').value, use_gitignore:$('#gitignore').checked, nb_outputs:$('#nbout').checked,
      save_as:$('#saveAs').value
    });
    if (!r.ok){ status(r.error, 'err'); return; }
    status('Done. ' + r.files + ' files bundled.', 'ok');
    showResult(r); renderSaved(r.saved); $('#saveAs').value = '';
    const s = await api('/api/state'); renderHistory(s.history, s.output_dir);
  } catch (e) { status('Could not reach the Ingot server. Is it still running?', 'err'); }
  finally { btn.disabled = false; }
};
$('#target').addEventListener('keydown', e => { if (e.key === 'Enter') $('#go').click(); });

api('/api/state').then(s => { renderSaved(s.saved); renderHistory(s.history, s.output_dir); });
setKind('github');
</script>
</body>
</html>
'''
