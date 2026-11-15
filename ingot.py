#!/usr/bin/env python3
"""
Ingot - melt a whole codebase into one AI-ready text file.

Clone a GitHub repo (or point at a local folder), and Ingot writes every
source file into a single, clearly separated .txt document with the path of
each file stated above its code. Zero dependencies: just Python 3.8+ and git.
"""

import argparse
import fnmatch
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

__version__ = "1.1.0"

CONFIG_DIR = Path(os.environ.get("INGOT_HOME", str(Path.home() / ".ingot")))
SAVED_FILE = CONFIG_DIR / "saved.json"

DEFAULT_SETTINGS = {"output_dir": "output", "max_kb": 500}

IGNORE_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv", "env",
    ".idea", ".vscode", "dist", "build", ".next", ".nuxt", "target", "out",
    ".cache", ".pytest_cache", ".mypy_cache", ".tox", "coverage", ".gradle",
    "vendor", "Pods", ".dart_tool", ".terraform", "bin", "obj",
}

IGNORE_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock",
    "Pipfile.lock", "composer.lock", "Cargo.lock", "Gemfile.lock", ".DS_Store",
    "Thumbs.db",
}

BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svgz", ".tiff",
    ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z", ".bz2", ".xz", ".jar", ".war",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".class", ".pyc",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv", ".flac", ".ogg",
    ".ttf", ".otf", ".woff", ".woff2", ".eot", ".psd", ".ai", ".sketch",
    ".db", ".sqlite", ".sqlite3", ".docx", ".xlsx", ".pptx", ".doc", ".xls",
    ".ppt", ".iso", ".dmg", ".apk", ".min.js", ".map",
}

LANG_BY_EXT = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript (jsx)",
    ".ts": "typescript", ".tsx": "typescript (tsx)", ".java": "java",
    ".c": "c", ".h": "c header", ".cpp": "c++", ".hpp": "c++ header",
    ".cs": "c#", ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php",
    ".swift": "swift", ".kt": "kotlin", ".dart": "dart", ".sh": "shell",
    ".bat": "batch", ".ps1": "powershell", ".html": "html", ".css": "css",
    ".scss": "scss", ".json": "json", ".yml": "yaml", ".yaml": "yaml",
    ".toml": "toml", ".xml": "xml", ".md": "markdown", ".sql": "sql",
    ".txt": "text", ".env": "env", ".ipynb": "jupyter notebook (converted to cells)", ".vue": "vue", ".svelte": "svelte",
}


class IngotError(Exception):
    pass


# --------------------------------------------------------------------------
# Saved shortcuts ("contacts")
# --------------------------------------------------------------------------

def owner_of(target):
    """GitHub account name from owner/repo or a GitHub URL (else None)."""
    t = (target or "").strip()
    m = re.match(r"^(?:https?://github\.com/|git@github\.com:)([\w.-]+)/", t)
    if m:
        return m.group(1)
    m = re.match(r"^([\w.-]+)/[\w.-]+$", t)
    return m.group(1) if m else None


def load_store():
    if SAVED_FILE.is_file():
        try:
            data = json.loads(SAVED_FILE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            data = {}
    else:
        data = {}
    data.setdefault("items", [])
    settings = dict(DEFAULT_SETTINGS)
    settings.update(data.get("settings", {}))
    data["settings"] = settings
    for item in data["items"]:
        if not item.get("account"):
            if item.get("type") == "github":
                item["account"] = owner_of(item.get("target"))
            elif item.get("type") == "account":
                item["account"] = item.get("target")
    return data


def save_store(data):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    SAVED_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def find_saved(data, name):
    for item in data["items"]:
        if item["name"].lower() == name.lower():
            return item
    return None


def add_saved(data, name, kind, target, branch=None):
    account = None
    if kind == "github":
        account = owner_of(target)
    elif kind == "account":
        account = target
    entry = {"name": name, "type": kind, "target": target, "branch": branch, "account": account}
    existing = find_saved(data, name)
    if existing:
        data["items"][data["items"].index(existing)] = entry
    else:
        data["items"].append(entry)
    # saving a repo also remembers the account it belongs to
    if kind == "github" and account:
        has_account = any(i["type"] == "account" and i["target"].lower() == account.lower() for i in data["items"])
        if not has_account and find_saved(data, account) is None:
            data["items"].append({"name": account, "type": "account", "target": account,
                                  "branch": None, "account": account})
    save_store(data)


# --------------------------------------------------------------------------
# GitHub helpers
# --------------------------------------------------------------------------

def normalize_repo(text):
    """Accept owner/repo, https URL, or git@ URL and return a clone URL."""
    text = text.strip()
    if re.match(r"^[\w.-]+/[\w.-]+$", text):
        return "https://github.com/{}.git".format(text)
    if text.startswith(("http://", "https://", "git@")):
        return text if text.endswith(".git") else text.rstrip("/") + ".git"
    raise IngotError("Could not understand repo '{}'. Use owner/repo or a full URL.".format(text))


def repo_name_from_url(url):
    name = url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name or "repo"


def _rmtree(path):
    def on_error(func, p, _exc):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=on_error)


def clone_repo(url, dest, branch=None, token=None):
    if shutil.which("git") is None:
        raise IngotError("git is not installed or not on PATH. Install it from https://git-scm.com")
    clone_url = url
    if token and url.startswith("https://"):
        clone_url = url.replace("https://", "https://{}@".format(token), 1)
    cmd = ["git", "clone", "--depth", "1"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [clone_url, str(dest)]
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        err = result.stderr.strip()
        if token:
            err = err.replace(token, "***")
        hint = ""
        if "not found" in err.lower() or "authentication" in err.lower():
            hint = "\nIf the repo is private, set GITHUB_TOKEN or pass --token."
        raise IngotError("git clone failed:\n{}{}".format(err, hint))


def list_account_repos(username, token=None):
    """Return a list of repo dicts for a GitHub user/org."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ingot-cli"}
    if token:
        headers["Authorization"] = "Bearer {}".format(token)

    def fetch(url):
        repos, page = [], 1
        while True:
            req = urllib.request.Request("{}{}page={}".format(url, "&" if "?" in url else "?", page), headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    batch = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise IngotError("GitHub user '{}' not found.".format(username))
                if e.code in (401, 403):
                    raise IngotError("GitHub API refused the request (rate limit or bad token).")
                raise IngotError("GitHub API error {}".format(e.code))
            except urllib.error.URLError as e:
                raise IngotError("Network error: {}".format(e.reason))
            if not batch:
                break
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return repos

    repos = []
    if token:
        try:
            mine = fetch("https://api.github.com/user/repos?per_page=100&affiliation=owner,collaborator")
            repos = [r for r in mine if r["owner"]["login"].lower() == username.lower()]
        except IngotError:
            repos = []
    if not repos:
        repos = fetch("https://api.github.com/users/{}/repos?per_page=100".format(username))
    repos.sort(key=lambda r: r.get("pushed_at") or "", reverse=True)
    return repos


# --------------------------------------------------------------------------
# File collection
# --------------------------------------------------------------------------

def load_gitignore(root):
    patterns = []
    gi = Path(root) / ".gitignore"
    if gi.is_file():
        for line in gi.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if line and not line.startswith(("#", "!")):
                patterns.append(line)
    return patterns


def matches_patterns(rel, name, is_dir, patterns):
    for p in patterns:
        dir_only = p.endswith("/")
        p = p.rstrip("/")
        if dir_only and not is_dir:
            continue
        anchored = p.startswith("/")
        p = p.lstrip("/")
        if anchored or "/" in p:
            if fnmatch.fnmatch(rel, p) or rel.startswith(p + "/"):
                return True
        elif fnmatch.fnmatch(name, p):
            return True
    return False


def is_binary(path):
    if path.suffix.lower() in BINARY_EXTS or path.name.endswith(".min.js"):
        return True
    try:
        with open(path, "rb") as f:
            return b"\0" in f.read(2048)
    except OSError:
        return True


def collect_files(root, excludes=None, include_exts=None, max_kb=500, use_gitignore=True):
    """Walk root and return (files, skipped). files is a list of (rel_path, abs_path)."""
    root = Path(root)
    patterns = list(excludes or [])
    if use_gitignore:
        patterns += load_gitignore(root)
    include = None
    if include_exts:
        include = {e if e.startswith(".") else "." + e for e in (x.lower() for x in include_exts)}

    files, skipped = [], []
    for dirpath, dirnames, filenames in os.walk(str(root)):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        rel_dir = "" if rel_dir == "." else rel_dir
        kept = []
        for d in sorted(dirnames):
            rel = "{}/{}".format(rel_dir, d) if rel_dir else d
            if d in IGNORE_DIRS or matches_patterns(rel, d, True, patterns):
                continue
            kept.append(d)
        dirnames[:] = kept

        for fname in sorted(filenames):
            rel = "{}/{}".format(rel_dir, fname) if rel_dir else fname
            path = Path(dirpath) / fname
            if fname in IGNORE_FILES or matches_patterns(rel, fname, False, patterns):
                continue
            if include and path.suffix.lower() not in include:
                continue
            if is_binary(path):
                skipped.append((rel, "binary"))
                continue
            try:
                size_kb = path.stat().st_size / 1024.0
            except OSError:
                skipped.append((rel, "unreadable"))
                continue
            if size_kb > (max(max_kb, 20480) if path.suffix.lower() == ".ipynb" else max_kb):
                skipped.append((rel, "too large ({:.0f} KB)".format(size_kb)))
                continue
            files.append((rel, path))
    return files, skipped


# --------------------------------------------------------------------------
# Output building
# --------------------------------------------------------------------------

def build_tree(paths):
    tree = {}
    for p in paths:
        node = tree
        for part in p.split("/"):
            node = node.setdefault(part, {})
    lines = []

    def walk(node, prefix=""):
        items = sorted(node.items(), key=lambda kv: (not kv[1], kv[0].lower()))
        for i, (name, child) in enumerate(items):
            last = i == len(items) - 1
            lines.append("{}{}{}{}".format(prefix, "`-- " if last else "|-- ", name, "/" if child else ""))
            if child:
                walk(child, prefix + ("    " if last else "|   "))

    walk(tree)
    return "\n".join(lines)


def _nb_outputs(outputs):
    chunks = []
    for o in outputs:
        otype = o.get("output_type")
        if otype == "stream":
            text = o.get("text", "")
        elif otype in ("execute_result", "display_data"):
            text = (o.get("data") or {}).get("text/plain", "")
        elif otype == "error":
            text = "{}: {}".format(o.get("ename", "Error"), o.get("evalue", ""))
        else:
            text = ""
        if isinstance(text, list):
            text = "".join(text)
        text = text.strip()
        if text:
            if len(text) > 2000:
                text = text[:2000] + "\n... [output truncated]"
            chunks.append(text)
    return "\n".join(chunks)


def notebook_to_text(path, include_outputs=False):
    """Turn a .ipynb into readable cell-by-cell text (images and metadata dropped)."""
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    try:
        nb = json.loads(raw)
    except ValueError:
        return raw
    cells = nb.get("cells")
    if cells is None:  # old nbformat 3
        cells = []
        for ws in nb.get("worksheets", []):
            cells.extend(ws.get("cells", []))
    parts = []
    for i, cell in enumerate(cells, 1):
        src = cell.get("source", cell.get("input", ""))
        if isinstance(src, list):
            src = "".join(src)
        src = src.rstrip()
        ctype = cell.get("cell_type", "code")
        if not src and ctype != "code":
            continue
        if ctype == "markdown":
            body = "\n".join(("# " + ln) if ln else "#" for ln in src.splitlines())
            parts.append("# %% [markdown] cell {}\n{}".format(i, body))
        elif ctype == "code":
            if not src and not (include_outputs and cell.get("outputs")):
                continue
            parts.append("# %% [code] cell {}\n{}".format(i, src))
            if include_outputs:
                out = _nb_outputs(cell.get("outputs", []))
                if out:
                    body = "\n".join("# " + ln for ln in out.splitlines())
                    parts.append("# --- output ---\n" + body)
        else:
            parts.append("# %% [{}] cell {}\n{}".format(ctype, i, src))
    return "\n\n".join(parts)


def read_text(path, nb_outputs=False):
    path = Path(path)
    if path.suffix.lower() == ".ipynb":
        return notebook_to_text(path, nb_outputs)
    return path.read_text(encoding="utf-8", errors="replace")


def build_document(project, source, files, skipped, nb_outputs=False):
    bar = "=" * 80
    thin = "-" * 80
    contents, total_lines, total_chars = [], 0, 0
    for rel, path in files:
        text = read_text(path, nb_outputs)
        contents.append((rel, text))
        total_lines += len(text.splitlines())
        total_chars += len(text)

    out = []
    out.append(bar)
    out.append("PROJECT   : {}".format(project))
    out.append("SOURCE    : {}".format(source))
    out.append("GENERATED : {}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    out.append("FILES     : {}   LINES: {}   APPROX TOKENS: {:,}".format(len(files), total_lines, total_chars // 4))
    out.append("TOOL      : Ingot v{}".format(__version__))
    out.append(bar)
    out.append("")
    out.append("DIRECTORY STRUCTURE")
    out.append(thin)
    out.append(build_tree([r for r, _ in contents]) or "(no files)")
    out.append("")

    for i, (rel, text) in enumerate(contents, 1):
        ext = Path(rel).suffix.lower()
        lang = LANG_BY_EXT.get(ext, ext.lstrip(".") or "text")
        out.append("")
        out.append(bar)
        out.append("FILE {}/{}: {}".format(i, len(contents), rel))
        out.append("LANGUAGE: {}   LINES: {}".format(lang, len(text.splitlines())))
        out.append(bar)
        out.append(text.rstrip("\n"))
        out.append("")
        out.append("[END OF FILE: {}]".format(rel))

    if skipped:
        out.append("")
        out.append(bar)
        out.append("SKIPPED FILES ({})".format(len(skipped)))
        out.append(bar)
        for rel, why in skipped:
            out.append("- {}  [{}]".format(rel, why))

    out.append("")
    out.append("=== END OF {} ===".format(project.upper()))
    return "\n".join(out) + "\n", total_lines, total_chars // 4


def safe_name(text):
    return re.sub(r"[^\w.-]+", "_", text).strip("_") or "project"


# --------------------------------------------------------------------------
# Core job
# --------------------------------------------------------------------------

def run_job(kind, target, opts):
    """kind: 'github' or 'local'. Returns a dict describing the result."""
    log = opts.get("log") or print
    out_dir = Path(opts["output_dir"]).expanduser()
    tmp = None
    try:
        if kind == "github":
            url = normalize_repo(target)
            project = repo_name_from_url(url)
            tmp = tempfile.mkdtemp(prefix="ingot_")
            log("Cloning {} ...".format(url))
            clone_repo(url, os.path.join(tmp, "repo"), opts.get("branch"), opts.get("token"))
            root = Path(tmp) / "repo"
            source = url
        else:
            root = Path(target).expanduser().resolve()
            if not root.is_dir():
                raise IngotError("Folder not found: {}".format(root))
            project = root.name or "project"
            source = str(root)

        log("Scanning files ...")
        files, skipped = collect_files(
            root, opts.get("excludes"), opts.get("exts"), opts.get("max_kb", 500),
            opts.get("use_gitignore", True),
        )
        if not files:
            raise IngotError("No readable code files found (check your filters).")

        doc, lines, tokens = build_document(project, source, files, skipped, opts.get("nb_outputs", False))
        project_dir = out_dir / safe_name(project)
        project_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_path = project_dir / "{}_{}.txt".format(safe_name(project), stamp)
        out_path.write_text(doc, encoding="utf-8")
        log("Done. {} files, {:,} lines, ~{:,} tokens".format(len(files), lines, tokens))
        if skipped:
            log("Skipped {} files (binary / too large). Listed at the end of the output.".format(len(skipped)))
        log("Saved to: {}".format(out_path.resolve()))
        return {"path": out_path, "project": project, "source": source, "files": len(files),
                "lines": lines, "tokens": tokens, "skipped": len(skipped), "text": doc}
    finally:
        if tmp:
            _rmtree(tmp)


# --------------------------------------------------------------------------
# Interactive mode
# --------------------------------------------------------------------------

def ask(prompt, default=None):
    suffix = " [{}]".format(default) if default else ""
    try:
        val = input("{}{}: ".format(prompt, suffix)).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return val or (default or "")


def choose(title, options, allow_back=True):
    """Return the 0-based index of the chosen option, or None for back/quit."""
    print("\n" + title)
    for i, opt in enumerate(options, 1):
        print("  {}) {}".format(i, opt))
    print("  0) {}".format("Back" if allow_back else "Quit"))
    while True:
        val = ask("Pick a number")
        if val.isdigit():
            n = int(val)
            if n == 0:
                return None
            if 1 <= n <= len(options):
                return n - 1
        print("Please enter a number from the list.")


def yes(prompt, default=False):
    val = ask("{} ({})".format(prompt, "Y/n" if default else "y/N")).lower()
    if not val:
        return default
    return val.startswith("y")


def base_opts(store, args=None):
    s = store["settings"]
    return {
        "output_dir": getattr(args, "out", None) or s["output_dir"],
        "max_kb": getattr(args, "max_kb", None) or s["max_kb"],
        "excludes": getattr(args, "exclude", None) or [],
        "exts": getattr(args, "ext", None) or [],
        "use_gitignore": not getattr(args, "no_gitignore", False),
        "branch": getattr(args, "branch", None),
        "token": getattr(args, "token", None) or os.environ.get("GITHUB_TOKEN"),
        "nb_outputs": getattr(args, "nb_outputs", False),
    }


def safe_run(kind, target, opts):
    try:
        run_job(kind, target, opts)
    except IngotError as e:
        print("\nError: {}".format(e))


def maybe_save(store, kind, target, branch=None):
    if yes("Save this for next time?"):
        default_name = repo_name_from_url(target) if kind != "local" else Path(target).name
        name = ask("Nickname", default_name)
        add_saved(store, name, kind, target, branch)
        account = owner_of(target) if kind == "github" else None
        print("Saved as '{}'{}.".format(name, " under account @{}".format(account) if account else ""))


def flow_github_repo(store, opts):
    target = ask("GitHub repo (owner/repo or URL)")
    if not target:
        return
    branch = ask("Branch (blank for default)") or None
    opts = dict(opts, branch=branch)
    try:
        normalize_repo(target)
    except IngotError as e:
        print("Error: {}".format(e))
        return
    safe_run("github", target, opts)
    maybe_save(store, "github", target, branch)


def browse_account(store, user, opts):
    try:
        print("Fetching repos ...")
        repos = list_account_repos(user, opts.get("token"))
    except IngotError as e:
        print("Error: {}".format(e))
        return
    if not repos:
        print("No repos found.")
        return
    labels = ["{}{}".format(r["name"], "  - " + r["description"][:60] if r.get("description") else "") for r in repos]
    idx = choose("Repos for {} (newest activity first)".format(user), labels)
    if idx is None:
        return
    full = repos[idx]["full_name"]
    safe_run("github", full, opts)
    maybe_save(store, "github", full)


def flow_github_account(store, opts):
    user = ask("GitHub username or org")
    if not user:
        return
    if find_saved(store, user) is None and yes("Save '{}' as an account shortcut?".format(user)):
        add_saved(store, user, "account", user)
    browse_account(store, user, opts)


def flow_local(store, opts):
    target = ask("Path to local folder")
    if not target:
        return
    target = target.strip('"').strip("'")
    safe_run("local", target, opts)
    if Path(target).expanduser().is_dir():
        maybe_save(store, "local", str(Path(target).expanduser().resolve()))


def saved_accounts(store):
    names = []
    for i in store["items"]:
        acc = i.get("account")
        if i["type"] in ("account", "github") and acc and acc.lower() not in [n.lower() for n in names]:
            names.append(acc)
    return names


def repos_of(store, account):
    return [i for i in store["items"]
            if i["type"] == "github" and (i.get("account") or "").lower() == account.lower()]


def print_saved(store):
    if not store["items"]:
        print("Nothing saved yet.")
        return
    for acc in saved_accounts(store):
        print("@{}".format(acc))
        for r in repos_of(store, acc):
            br = "  [{}]".format(r["branch"]) if r.get("branch") else ""
            print("    {}  ->  {}{}".format(r["name"], r["target"], br))
    for i in store["items"]:
        if i["type"] == "local":
            print("[local] {}  ->  {}".format(i["name"], i["target"]))


def flow_saved_account(store, account, opts):
    repos = repos_of(store, account)
    labels = ["Browse all repos on GitHub"] + ["{}  ->  {}".format(r["name"], r["target"]) for r in repos]
    idx = choose("@{}".format(account), labels)
    if idx is None:
        return
    if idx == 0:
        browse_account(store, account, opts)
    else:
        item = repos[idx - 1]
        safe_run("github", item["target"], dict(opts, branch=item.get("branch") or opts.get("branch")))


def flow_saved(store, opts):
    if not store["items"]:
        print("\nNothing saved yet. Run a job and choose 'Save this for next time'.")
        return
    accounts = saved_accounts(store)
    locals_ = [i for i in store["items"] if i["type"] == "local"]
    labels = ["@{}  (account, {} saved repos)".format(a, len(repos_of(store, a))) for a in accounts]
    labels += ["[local] {}  ->  {}".format(i["name"], i["target"]) for i in locals_]
    idx = choose("Saved shortcuts", labels)
    if idx is None:
        return
    if idx < len(accounts):
        flow_saved_account(store, accounts[idx], opts)
    else:
        item = locals_[idx - len(accounts)]
        safe_run("local", item["target"], opts)


def flow_manage(store):
    while True:
        choice = choose("Manage saved", ["Add shortcut", "Remove shortcut", "List shortcuts"])
        if choice is None:
            return
        if choice == 0:
            kind_idx = choose("Type", ["GitHub repo", "GitHub account", "Local folder"])
            if kind_idx is None:
                continue
            kind = ["github", "account", "local"][kind_idx]
            target = ask("Target (owner/repo, username, or folder path)")
            name = ask("Nickname", repo_name_from_url(target) if target else "")
            if target and name:
                add_saved(store, name, kind, target)
                print("Saved.")
        elif choice == 1:
            if not store["items"]:
                print("Nothing to remove.")
                continue
            idx = choose("Remove which?", [i["name"] for i in store["items"]])
            if idx is not None:
                gone = store["items"].pop(idx)
                save_store(store)
                print("Removed '{}'.".format(gone["name"]))
        else:
            print_saved(store)


def flow_settings(store):
    s = store["settings"]
    print("\nCurrent settings: output folder = {}, max file size = {} KB".format(s["output_dir"], s["max_kb"]))
    s["output_dir"] = ask("Output folder", s["output_dir"])
    kb = ask("Max file size in KB", str(s["max_kb"]))
    s["max_kb"] = int(kb) if kb.isdigit() else s["max_kb"]
    save_store(store)
    print("Settings saved.")


def start_web(store, port=8765, open_browser=True):
    try:
        import ingot_web
    except ImportError:
        print("Error: ingot_web.py must sit in the same folder as ingot.py.")
        return
    ingot_web.serve(store, port, open_browser)


def interactive(store, args):
    print("\n  INGOT  v{}  -  melt a codebase into one AI-ready file".format(__version__))
    while True:
        opts = base_opts(store, args)
        choice = choose(
            "What do you want to bundle?",
            ["GitHub repo", "GitHub account (browse repos)", "Local folder", "Saved shortcuts",
             "Manage saved", "Settings", "Start local web UI"],
            allow_back=False,
        )
        if choice is None:
            print("Bye.")
            return
        if choice == 0:
            flow_github_repo(store, opts)
        elif choice == 1:
            flow_github_account(store, opts)
        elif choice == 2:
            flow_local(store, opts)
        elif choice == 3:
            flow_saved(store, opts)
        elif choice == 4:
            flow_manage(store)
        elif choice == 5:
            flow_settings(store)
        elif choice == 6:
            start_web(store)


# --------------------------------------------------------------------------
# Command line
# --------------------------------------------------------------------------

def add_common(p):
    p.add_argument("-o", "--out", help="output folder (default: ./output)")
    p.add_argument("-e", "--exclude", action="append", help="glob pattern to skip (repeatable)")
    p.add_argument("--ext", action="append", help="only include this extension, e.g. py (repeatable)")
    p.add_argument("--max-kb", type=int, help="skip files larger than this many KB (default 500)")
    p.add_argument("--no-gitignore", action="store_true", help="do not honor the repo's .gitignore")
    p.add_argument("--nb-outputs", action="store_true", help="include text outputs of Jupyter notebook cells")


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ingot",
        description="Melt a GitHub repo or local folder into one AI-ready text file. "
                    "Run with no arguments for the interactive menu.",
    )
    parser.add_argument("-v", "--version", action="version", version="ingot " + __version__)
    sub = parser.add_subparsers(dest="cmd")

    g = sub.add_parser("github", help="bundle a GitHub repo")
    g.add_argument("repo", help="owner/repo or full URL")
    g.add_argument("-b", "--branch", help="branch or tag")
    g.add_argument("--token", help="GitHub token for private repos (or set GITHUB_TOKEN)")
    g.add_argument("--save", metavar="NAME", help="also save this repo under a nickname")
    add_common(g)

    l = sub.add_parser("local", help="bundle a local folder")
    l.add_argument("path", help="folder path")
    l.add_argument("--save", metavar="NAME", help="also save this folder under a nickname")
    add_common(l)

    r = sub.add_parser("run", help="run a saved shortcut by nickname")
    r.add_argument("name")
    r.add_argument("--token", help="GitHub token (or set GITHUB_TOKEN)")
    add_common(r)

    sub.add_parser("list", help="list saved shortcuts")

    w = sub.add_parser("web", help="start the local web UI")
    w.add_argument("--port", type=int, default=8765, help="port (default 8765)")
    w.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")

    rm = sub.add_parser("remove", help="remove a saved shortcut")
    rm.add_argument("name")

    sv = sub.add_parser("save", help="save a shortcut without running it")
    sv.add_argument("name")
    sv.add_argument("kind", choices=["github", "account", "local"])
    sv.add_argument("target")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    store = load_store()

    if not args.cmd:
        interactive(store, args)
        return 0

    try:
        if args.cmd == "list":
            print_saved(store)
        elif args.cmd == "web":
            start_web(store, args.port, not args.no_browser)
        elif args.cmd == "remove":
            item = find_saved(store, args.name)
            if not item:
                raise IngotError("No saved shortcut named '{}'.".format(args.name))
            store["items"].remove(item)
            save_store(store)
            print("Removed '{}'.".format(args.name))
        elif args.cmd == "save":
            add_saved(store, args.name, args.kind, args.target)
            print("Saved '{}'.".format(args.name))
        elif args.cmd in ("github", "local"):
            target = args.repo if args.cmd == "github" else args.path
            run_job(args.cmd, target, base_opts(store, args))
            if args.save:
                add_saved(store, args.save, args.cmd, target, getattr(args, "branch", None))
                print("Saved as '{}'.".format(args.save))
        elif args.cmd == "run":
            item = find_saved(store, args.name)
            if not item:
                raise IngotError("No saved shortcut named '{}'.".format(args.name))
            if item["type"] == "account":
                raise IngotError("'{}' is an account shortcut. Run 'ingot' and browse its repos.".format(args.name))
            opts = base_opts(store, args)
            opts["branch"] = item.get("branch")
            run_job(item["type"], item["target"], opts)
    except IngotError as e:
        print("Error: {}".format(e), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
