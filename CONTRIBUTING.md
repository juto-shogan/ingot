# Contributing to Ingot

Thanks for wanting to help! Ingot is a small, friendly project, and **beginners are very welcome**. You do not need to be an expert. Many of the best contributions are small ones.

## Ways to help (no big commitment needed)

- **Try it and report what breaks.** Run Ingot on your own projects, on your operating system, and open an issue if something feels wrong or confusing.
- **Improve the docs.** Fix a typo, clarify a confusing step, or translate the README.
- **Pick a `good first issue`.** Look at the [issues tab](../../issues) and filter by that label. Each one is small and says where in the code to look.
- **Add tests.** More tests make everyone safer to change things.
- **Suggest ideas.** Open an issue and describe what you wish Ingot could do.

If you are not sure where to start, open an issue and say hi. We will point you to something.

## Setting up

You need **Python 3.8 or newer** and **Git**. There is nothing else to install.

```powershell
# 1. Fork the repo on GitHub (button at the top right), then clone YOUR fork
git clone https://github.com/<your-username>/ingot.git
cd ingot

# 2. Run it to make sure it works
python ingot.py --version
python ingot.py local .
```

On macOS or Linux, use `python3` instead of `python`.

## Running the tests

Tests use Python's built-in `unittest`, so no extra packages are needed.

```powershell
python -m unittest discover -s tests -v
```

All tests should pass before you open a pull request.

## How to make a change

1. **Create a branch** for your work. Use a short, descriptive name:
   ```powershell
   git checkout -b fix-readme-typo
   ```
2. **Make your change.** Keep it focused: one pull request should do one thing.
3. **Run the tests** (see above). If you added a feature or fixed a bug, add a test for it.
4. **Commit** with a clear message:
   ```powershell
   git add .
   git commit -m "Fix typo in README setup section"
   ```
5. **Push** to your fork and **open a pull request** on GitHub:
   ```powershell
   git push origin fix-readme-typo
   ```
6. Describe what you changed and why. If it fixes an issue, write `Fixes #12` in the description.

A maintainer will review it, usually within a few days. We may ask for small changes. That is normal and not a criticism.

## Project layout

```
ingot.py          the CLI: file collection, bundling, saved shortcuts, menus
ingot_web.py      the local web UI (a small server plus one embedded HTML page)
tests/            unit tests
README.md         user documentation
```

Useful places to know:

| What | Where in `ingot.py` |
|------|---------------------|
| Folders and files that get skipped | `IGNORE_DIRS`, `IGNORE_FILES`, `BINARY_EXTS` |
| File extension to language names | `LANG_BY_EXT` |
| Walking a project and filtering files | `collect_files` |
| The output text format | `build_document` |
| Notebook (`.ipynb`) conversion | `notebook_to_text` |
| Saved shortcuts | `add_saved`, `load_store` |
| Command-line options | `build_parser` |

## Code guidelines

- **No new dependencies.** Ingot uses only the Python standard library. This is a core feature, so please keep it that way.
- **Stay compatible with Python 3.8.** Avoid newer syntax such as `match` statements or `X | Y` type hints.
- **Keep it readable.** Clear names and short functions beat clever code. Add a short comment when something is not obvious.
- **Windows matters.** Many users are on Windows, so avoid assuming Unix paths, and test with spaces in folder names when you can.
- **Match the existing style.** Four-space indentation, double quotes, and `.format()` for strings.

## Pull request checklist

- [ ] The tests pass (`python -m unittest discover -s tests -v`)
- [ ] I added or updated tests if I changed behavior
- [ ] I updated the README if I added or changed an option
- [ ] My change does one thing and the description explains it

## Reporting bugs

Open an issue and include:

- Your operating system and Python version (`python --version`)
- The exact command you ran
- What you expected, and what happened instead (copy the error text)

## Be kind

Everyone here is learning. Be patient, be respectful, and assume good intent. Questions are always welcome, and there are no silly ones.

By contributing, you agree that your work will be released under the project's [MIT License](LICENSE).
