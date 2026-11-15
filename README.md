# Ingot

**Melt an entire codebase into one AI-ready text file.**

Ingot takes a GitHub repo or a folder on your computer and writes all of its code into a single, cleanly separated `.txt` file. The path of every file is stated above its code, so an AI knows exactly where each piece lives. Upload one file instead of fifty.

It comes with a **command-line menu** and a **local web page** where you paste a URL, click Extract, and copy the result.

---

## Features

- **GitHub or local:** bundle a public or private repo, browse all repos of a GitHub account, or bundle any folder on your machine
- **Local web UI:** paste a link or folder path in your browser, then copy or download the bundle
- **Saved shortcuts, organized by account:** save repos, GitHub accounts and folders once, then reuse them by nickname. Repos are grouped under the account they belong to
- **Organized output:** every project gets its own folder inside `output/`
- **Jupyter notebooks (`.ipynb`):** converted to clean cell-by-cell text, with images and metadata stripped
- **Smart filtering:** skips `.git`, `node_modules`, build folders, lock files, binaries and oversized files, and respects `.gitignore`
- **Token estimate:** see roughly how many tokens the bundle uses
- **No dependencies:** just Python 3.8+ and git

---

## Setup (Windows)

1. Install [Python](https://www.python.org/downloads/) (tick **"Add python.exe to PATH"** in the installer) and [Git](https://git-scm.com/download/win)
2. Download the project:

```powershell
git clone https://github.com/juto-shogan/ingot.git
cd ingot
```

3. Run it:

```powershell
python ingot.py
```

That is all. No install step is needed. Keep `ingot.py` and `ingot_web.py` in the same folder.

> **Optional: use the short `ingot` command.** Run `python -m pip install .` inside the folder. If Windows then says `ingot` is not recognized, the Python Scripts folder is not on your PATH. Either add it, or just keep using `python ingot.py` or `python -m ingot`. Everything below works with either.

**macOS / Linux:** the same steps work, with `python3` instead of `python`.

---

## Using the menu

```powershell
python ingot.py
```

```
What do you want to bundle?
  1) GitHub repo
  2) GitHub account (browse repos)
  3) Local folder
  4) Saved shortcuts
  5) Manage saved
  6) Settings
  7) Start local web UI
  0) Quit
```

After each run, Ingot offers to save the source for next time.

---

## Using the web UI

```powershell
python ingot.py web
```

Your browser opens at `http://127.0.0.1:8765`.

1. Choose **GitHub** or **Local folder**
2. Paste a repo URL (or `owner/repo`), or type the full folder path
3. Click **Extract**
4. Click **Copy all text** and paste it into your AI, or **Download .txt**

The page also shows your saved shortcuts (click one to fill the form, or use *browse repos* on an account) and your recent bundles.

The server only listens on your own computer. Other devices and other websites cannot reach it. Stop it with `Ctrl+C`.

Options: `--port 9000` to change the port, `--no-browser` to skip opening the browser.

---

## Command mode

```powershell
# GitHub repo (owner/repo or full URL)
python ingot.py github octocat/Hello-World
python ingot.py github octocat/Hello-World --branch main

# Local folder
python ingot.py local C:\Users\you\projects\my-app

# Save while running, then rerun by nickname
python ingot.py github octocat/Hello-World --save hello
python ingot.py run hello
```

### Saved shortcuts

Shortcuts live in `~/.ingot/saved.json` (on Windows: `C:\Users\you\.ingot\saved.json`).

| Type | Stores | Example |
|------|--------|---------|
| `github` | a repo, remembered under its account | `octocat/Hello-World` |
| `account` | a GitHub username or org, so you can browse its repos | `octocat` |
| `local` | a folder path | `C:\projects\app` |

Saving a repo automatically saves its **account name** too, so you can come back and browse that account's other repos. Shortcuts are displayed grouped by account:

```
@octocat
    hello  ->  octocat/Hello-World
    spoon  ->  octocat/Spoon-Knife
[local] myapp  ->  C:\projects\app
```

```powershell
python ingot.py save work github mycompany/api
python ingot.py save me account my-username
python ingot.py list
python ingot.py run work
python ingot.py remove work
```

---

## Output

Each project gets its own folder:

```
output/
  my-app/
    my-app_20261115-101302.txt
    my-app_20261116-093011.txt
  Hello-World/
    Hello-World_20261115-101300.txt
```

Inside a bundle:

```
================================================================================
PROJECT   : my-app
SOURCE    : https://github.com/me/my-app.git
GENERATED : 2026-11-15 10:13:02
FILES     : 12   LINES: 840   APPROX TOKENS: 7,350
================================================================================

DIRECTORY STRUCTURE
--------------------------------------------------------------------------------
|-- src/
|   `-- app.py
`-- README.md

================================================================================
FILE 1/12: README.md
LANGUAGE: markdown   LINES: 24
================================================================================
...file contents...

[END OF FILE: README.md]
```

Skipped files (binary, too large) are listed at the bottom so nothing disappears silently.

### Jupyter notebooks

`.ipynb` files are converted to readable text instead of raw JSON:

```
# %% [markdown] cell 1
# # Title
# Some intro

# %% [code] cell 2
import pandas as pd
print('hi')
```

Cell outputs, which can be huge, are left out by default. Add `--nb-outputs` (or tick the box in the web UI) to include text outputs. Images are always dropped.

---

## Options

| Flag | Description |
|------|-------------|
| `-o, --out DIR` | output folder (default `output`) |
| `-b, --branch NAME` | branch or tag to clone (GitHub only) |
| `-e, --exclude PATTERN` | glob to skip, repeatable (e.g. `-e "*.test.js" -e "docs/*"`) |
| `--ext EXT` | only include these extensions, repeatable (e.g. `--ext py --ext md`) |
| `--max-kb N` | skip files larger than N KB (default 500) |
| `--no-gitignore` | do not honor the project's `.gitignore` |
| `--nb-outputs` | include text outputs from notebook cells |
| `--token TOKEN` | GitHub token for private repos |
| `--save NAME` | save the source as a shortcut after running |

### Private repos

Set a GitHub token once and Ingot uses it automatically.

```powershell
# PowerShell (current window)
$env:GITHUB_TOKEN = "ghp_yourtoken"

# Permanent
setx GITHUB_TOKEN "ghp_yourtoken"
```

The token is used only for cloning and the GitHub API. It is never written to disk or into the output file.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `'python' is not recognized` | Reinstall Python and tick "Add to PATH", or try `py ingot.py` |
| `'ingot' is not recognized` | Use `python ingot.py` instead, or add Python's Scripts folder to PATH |
| `git is not installed` | Install Git, then reopen the terminal |
| `git clone failed` on a private repo | Set `GITHUB_TOKEN` or pass `--token` |
| `GitHub API refused the request` | Rate limit reached. Set `GITHUB_TOKEN` |
| `No readable code files found` | Check your extension and exclude filters |
| Web page says it cannot reach the server | The terminal running `python ingot.py web` was closed. Start it again |
| Bundle too big for your AI | Filter with `--ext`, `-e` or `--max-kb` |

---

## Roadmap

- Split a bundle into multiple parts for small context windows
- Option to strip comments and blank lines
- Nested `.gitignore` support
- Account browsing with a token for private repos in the web UI

---

## License

MIT
