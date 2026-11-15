# Starter issues for Ingot

Paste each one into GitHub as a new issue. Create these labels first (Issues > Labels):
`good first issue`, `help wanted`, `documentation`, `tests`, `enhancement`.

Do **not** commit this file to the repo. It is just your copy-paste sheet.

---

## 1. Add more file extensions to the language list

**Labels:** `good first issue`, `enhancement`

Ingot labels each bundled file with a language name (for example `.py` becomes `python`). Some common extensions are missing, so those files show only the raw extension.

**Where to look:** the `LANG_BY_EXT` dictionary near the top of `ingot.py`.

**Your task:**
- Add at least 5 extensions that are missing (ideas: `.lua`, `.r`, `.scala`, `.zig`, `.ex`, `.exs`, `.hs`, `.jl`, `.tf`, `.graphql`, `.proto`, `.gradle`).
- Run `python -m unittest discover -s tests -v` to make sure everything still passes.

**Done when:** the new extensions appear in `LANG_BY_EXT` with sensible names, and tests pass.

---

## 2. Expand the default ignore lists

**Labels:** `good first issue`, `enhancement`

Ingot skips noisy folders and files by default (like `node_modules` and `package-lock.json`). Some common ones are still missing, which can bloat the output.

**Where to look:** `IGNORE_DIRS` and `IGNORE_FILES` near the top of `ingot.py`.

**Your task:**
- Add at least 5 more entries. Ideas for folders: `.svelte-kit`, `.angular`, `.turbo`, `__MACOSX`, `site-packages`, `.expo`. Ideas for files: `go.sum`, `uv.lock`, `npm-shrinkwrap.json`, `flake.lock`.
- Only add things that are clearly generated or dependency folders, not real source code.

**Done when:** the entries are added and tests pass. Bonus: add a test in `tests/test_ingot.py` for one of the new entries.

---

## 3. Test Ingot on macOS or Linux and report what you find

**Labels:** `good first issue`, `help wanted`

Ingot is developed mostly on Windows. We would like to know it works well elsewhere.

**Your task:**
1. Follow the setup steps in the README on macOS or Linux.
2. Try `python3 ingot.py`, a GitHub repo, a local folder, and `python3 ingot.py web`.
3. Comment on this issue with your OS, Python version, and what worked or broke. Open a separate issue for each bug.

**Done when:** you have posted your results. No code needed.

---

## 4. Add tests for the web UI helpers

**Labels:** `good first issue`, `tests`

The local web UI lives in `ingot_web.py`. Only one small helper (`split_csv`) is tested so far.

**Where to look:** `list_history` in `ingot_web.py` and the existing `WebHelperTests` class in `tests/test_ingot.py`.

**Your task:**
- Write tests for `list_history`: an empty folder returns an empty list, and bundles in project folders come back newest first.
- Create the files inside a temporary folder (see how other tests use `tempfile.TemporaryDirectory`).

**Done when:** at least 3 new tests exist and all tests pass.

---

## 5. Translate the README into your language

**Labels:** `good first issue`, `documentation`

Many developers read docs more comfortably in their own language.

**Your task:**
- Copy `README.md` to `README.<language-code>.md` (for example `README.fr.md`, `README.pt.md`, `README.ha.md`, `README.yo.md`, `README.ig.md`).
- Translate the text. Keep the commands and code blocks exactly as they are.
- Add a link to your translation at the top of `README.md`.

**Done when:** the translated file is added and linked. Native speakers only, please, and no machine-translated dumps without review.

---

## 6. Add a `--compact` option to shrink the output

**Labels:** `help wanted`, `enhancement`

AI context windows are limited. A `--compact` flag that collapses runs of blank lines would save tokens.

**Where to look:**
- `build_parser` and `add_common` in `ingot.py` for adding the flag
- `base_opts` for passing it through
- `build_document` for where file text is added to the output

**Your task:**
- Add `--compact` (off by default). When on, replace three or more consecutive blank lines with one.
- Make it work in the web UI too, if you are up for it (a checkbox in the Options section).
- Add tests and a line in the README options table.

**Done when:** the flag works, has tests, and is documented.

---

## 7. Add a `--copy` option to copy the result to the clipboard

**Labels:** `help wanted`, `enhancement`

After bundling, many people just want the text on their clipboard to paste into an AI chat.

**Your task:**
- Add `--copy`. After the file is written, copy its contents to the clipboard using only the standard library: `clip` on Windows, `pbcopy` on macOS, and `xclip` or `wl-copy` on Linux (via `subprocess`).
- If no clipboard tool is found, print a friendly message instead of crashing.
- Add a line in the README options table.

**Done when:** it works on at least one operating system, fails gracefully on others, and is documented. Say in your pull request which OS you tested on.

---

## 8. Support nested `.gitignore` files

**Labels:** `help wanted`, `enhancement`

Right now Ingot only reads the `.gitignore` in the project root. Real projects often have `.gitignore` files in subfolders too.

**Where to look:** `load_gitignore`, `matches_patterns` and `collect_files` in `ingot.py`.

**Your task:**
- While walking the project, also read a `.gitignore` found in each subfolder and apply its patterns to that folder's contents only.
- Add tests with a nested `.gitignore` in a temporary folder.

**Done when:** patterns in a subfolder's `.gitignore` apply only inside that folder, and tests cover it. This one is a bit harder, so ask questions in the issue if you get stuck.

---

### Tips for posting these

- Mark the first 5 as `good first issue` so beginners can find them easily.
- Reply to anyone who comments "can I take this?" within a day or two, even just to say yes.
- Pin issue 3 (macOS/Linux testing). It needs no code, so it is a gentle first step.
