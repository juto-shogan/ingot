# Ingot

**Melt an entire codebase into one AI-ready text file.**

Ingot clones a GitHub repo (or reads a local folder), pulls the code out of every file, and writes it all into a single, cleanly separated `.txt` document. Every file's path is stated above its code, so an AI can see exactly where each piece lives. Upload one file instead of fifty.

![Python](https://img.shields.io/badge/python-3.8%2B-blue) ![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen) ![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## Features

- **GitHub or local**: bundle a public or private repo, a whole GitHub account's repos, or any folder on your machine
- **Saved shortcuts**: keep repos, accounts and folders in a contact list and rerun them by nickname
- **Interactive menu**: run `ingot` with no arguments and pick what you want
- **Scriptable**: every action also works as a one-line command
- **Clean output**: header, directory tree, then each file under a banner with its path, language and line count
- **Smart filtering**: skips `.git`, `node_modules`, build folders, lock files, binaries and oversized files, and honors the repo's `.gitignore`
- **Token estimate**: shows an approximate token count so you know it fits your AI's context window
- **Zero dependencies**: only Python 3.8+ and `git`

---

## Installation

```bash
git clone https://github.com/<your-username>/ingot.git
cd ingot
pip install .
```

Now `ingot` works from anywhere. Prefer not to install? Run it directly:

```bash
python ingot.py
```

**Requirements:** Python 3.8+ and [git](https://git-scm.com) on your PATH.

---

## Quick start

### Interactive mode

```bash
ingot
```

```
What do you want to bundle?
  1) GitHub repo
  2) GitHub account (browse repos)
  3) Local folder
  4) Saved shortcuts
  5) Manage saved
  6) Settings
  0) Quit
```

After each run, Ingot offers to save the source so next time is two keystrokes.

### Command mode

```bash
# a GitHub repo (owner/repo or full URL)
ingot github torvalds/linux --branch master

# a local folder
ingot local ~/projects/my-app

# save while running, rerun later by nickname
ingot github octocat/Hello-World --save hello
ingot run hello
```

Your bundle lands in the `output/` folder as `<project>_<timestamp>.txt`.

---

## Saved shortcuts

Shortcuts live in `~/.ingot/saved.json` and come in three types:

| Type        | What it stores                                                | Example                      |
| ----------- | ------------------------------------------------------------- | ---------------------------- |
| `github`  | a single repo                                                 | `octocat/Hello-World`      |
| `account` | a GitHub user or org; Ingot lists their repos so you pick one | `octocat`                  |
| `local`   | a folder path                                                 | `C:\Users\me\projects\app` |

```bash
ingot save work-api github mycompany/api
ingot save me account my-username
ingot save notes local ~/notes
ingot list
ingot run work-api
ingot remove notes
```

---

## Options

| Flag                      | Description                                                            |
| ------------------------- | ---------------------------------------------------------------------- |
| `-o, --out DIR`         | output folder (default `./output`)                                   |
| `-b, --branch NAME`     | branch or tag to clone (GitHub only)                                   |
| `-e, --exclude PATTERN` | glob to skip, repeatable (e.g. `-e "*.test.js" -e "docs/*"`)         |
| `--ext EXT`             | only include these extensions, repeatable (e.g. `--ext py --ext md`) |
| `--max-kb N`            | skip files larger than N KB (default 500)                              |
| `--no-gitignore`        | do not honor the repo's `.gitignore`                                 |
| `--token TOKEN`         | GitHub token for private repos                                         |
| `--save NAME`           | save the source as a shortcut after running                            |

### Private repos

Set a token once and Ingot uses it automatically:

```bash
# macOS / Linux
export GITHUB_TOKEN=ghp_yourtoken

# Windows (PowerShell)
$env:GITHUB_TOKEN = "ghp_yourtoken"
```

The token is only used for the clone and the GitHub API. It is never written to disk or to the output file.

---

## Output format

```
================================================================================
PROJECT   : my-app
SOURCE    : https://github.com/me/my-app.git
GENERATED : 2026-11-15 09:25:36
FILES     : 12   LINES: 840   APPROX TOKENS: 7,350
TOOL      : Ingot v1.0.0
================================================================================

DIRECTORY STRUCTURE
--------------------------------------------------------------------------------
|-- src/
|   |-- app.py
|   `-- utils.py
`-- README.md


================================================================================
FILE 1/12: README.md
LANGUAGE: markdown   LINES: 24
================================================================================
...file contents...

[END OF FILE: README.md]
```

Skipped files (binary, too large) are listed at the bottom so nothing disappears silently.

---

## Using the output with AI

1. Run Ingot on the project.
2. Upload the `.txt` from `output/` to your AI of choice.
3. Ask away: *"Explain the architecture"*, *"Find the bug in the auth flow"*, *"Write tests for `src/utils.py`"*. The file paths in the banners let the AI reference exact locations.

If the file is too big, narrow it down with `--ext`, `-e` or `--max-kb`.

---

## What gets skipped by default

- **Folders:** `.git`, `node_modules`, `__pycache__`, `venv`, `dist`, `build`, `target`, `.next`, `vendor` and similar
- **Files:** lock files (`package-lock.json`, `yarn.lock`, ...), images, fonts, archives, executables, minified JS, source maps
- **Anything** matched by the project's root `.gitignore`
- **Anything** over the size limit

---

## Troubleshooting

| Problem                                | Fix                                                          |
| -------------------------------------- | ------------------------------------------------------------ |
| `git is not installed`               | Install git and reopen your terminal                         |
| `git clone failed` on a private repo | Set `GITHUB_TOKEN` or pass `--token`                     |
| `GitHub API refused the request`     | You hit the unauthenticated rate limit; set `GITHUB_TOKEN` |
| `No readable code files found`       | Check your `--ext` and `-e` filters                      |
| Output is too large for your AI        | Filter by extension, exclude folders, lower `--max-kb`     |

---

## Roadmap

- Split output into multiple parts for small context windows
- Strip comments and blank lines option
- Copy result straight to the clipboard
- Nested `.gitignore` support

---

## Contributing

Issues and pull requests are welcome. Ingot is a single file, `ingot.py`, so it is easy to read and hack on.

## License

MIT
