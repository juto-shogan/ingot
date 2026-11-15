"""Unit tests for Ingot. Run with:  python -m unittest discover -s tests -v"""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ingot  # noqa: E402
import ingot_web  # noqa: E402


def write(root, rel, content="x = 1\n", binary=False):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if binary:
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path


class NormalizeRepoTests(unittest.TestCase):
    def test_owner_slash_repo(self):
        self.assertEqual(ingot.normalize_repo("octocat/Hello-World"),
                         "https://github.com/octocat/Hello-World.git")

    def test_url_gets_git_suffix(self):
        self.assertEqual(ingot.normalize_repo("https://github.com/octocat/Hello-World"),
                         "https://github.com/octocat/Hello-World.git")

    def test_url_with_git_suffix_unchanged(self):
        url = "https://github.com/octocat/Hello-World.git"
        self.assertEqual(ingot.normalize_repo(url), url)

    def test_invalid_input_raises(self):
        with self.assertRaises(ingot.IngotError):
            ingot.normalize_repo("not a repo")

    def test_repo_name_from_url(self):
        self.assertEqual(ingot.repo_name_from_url("https://github.com/octocat/Hello-World.git"), "Hello-World")


class OwnerOfTests(unittest.TestCase):
    def test_short_form(self):
        self.assertEqual(ingot.owner_of("octocat/Hello-World"), "octocat")

    def test_url_form(self):
        self.assertEqual(ingot.owner_of("https://github.com/octocat/Hello-World"), "octocat")

    def test_ssh_form(self):
        self.assertEqual(ingot.owner_of("git@github.com:octocat/Hello-World.git"), "octocat")

    def test_empty(self):
        self.assertIsNone(ingot.owner_of(""))


class CollectFilesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def rels(self, **kwargs):
        files, skipped = ingot.collect_files(self.root, **kwargs)
        return [r for r, _ in files], skipped

    def test_collects_normal_files(self):
        write(self.root, "src/app.py")
        write(self.root, "README.md", "# hi\n")
        rels, _ = self.rels()
        self.assertEqual(sorted(rels), ["README.md", "src/app.py"])

    def test_ignores_default_folders(self):
        write(self.root, "src/app.py")
        write(self.root, "node_modules/lib/index.js")
        write(self.root, ".git/config", "[core]\n")
        rels, _ = self.rels()
        self.assertEqual(rels, ["src/app.py"])

    def test_ignores_lock_files(self):
        write(self.root, "app.py")
        write(self.root, "package-lock.json", "{}")
        rels, _ = self.rels()
        self.assertEqual(rels, ["app.py"])

    def test_binary_files_are_skipped_and_reported(self):
        write(self.root, "app.py")
        write(self.root, "data.bin2", b"\x00\x01\x02", binary=True)
        rels, skipped = self.rels()
        self.assertEqual(rels, ["app.py"])
        self.assertIn(("data.bin2", "binary"), skipped)

    def test_large_files_are_skipped(self):
        write(self.root, "big.txt", "a" * 3000)
        rels, skipped = self.rels(max_kb=1)
        self.assertEqual(rels, [])
        self.assertTrue(any(name == "big.txt" and "too large" in why for name, why in skipped))

    def test_honors_gitignore(self):
        write(self.root, ".gitignore", "*.log\nsecret/\n")
        write(self.root, "keep.py")
        write(self.root, "debug.log", "noise")
        write(self.root, "secret/key.py")
        rels, _ = self.rels()
        self.assertIn("keep.py", rels)
        self.assertNotIn("debug.log", rels)
        self.assertNotIn("secret/key.py", rels)

    def test_gitignore_can_be_disabled(self):
        write(self.root, ".gitignore", "*.log\n")
        write(self.root, "debug.log", "noise")
        rels, _ = self.rels(use_gitignore=False)
        self.assertIn("debug.log", rels)

    def test_extension_filter(self):
        write(self.root, "a.py")
        write(self.root, "b.js")
        rels, _ = self.rels(include_exts=["py"])
        self.assertEqual(rels, ["a.py"])

    def test_exclude_pattern(self):
        write(self.root, "a.py")
        write(self.root, "tests/test_a.py")
        rels, _ = self.rels(excludes=["tests/*"])
        self.assertEqual(rels, ["a.py"])


class NotebookTests(unittest.TestCase):
    def make_notebook(self):
        nb = {
            "cells": [
                {"cell_type": "markdown", "source": ["# Title\n", "Intro"]},
                {"cell_type": "code", "source": ["print('hi')"], "outputs": [
                    {"output_type": "stream", "name": "stdout", "text": ["hi\n"]},
                    {"output_type": "display_data", "data": {"image/png": "AAAA" * 500, "text/plain": ["<Figure>"]}},
                ]},
                {"cell_type": "code", "source": [], "outputs": []},
            ],
            "metadata": {}, "nbformat": 4, "nbformat_minor": 5,
        }
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "demo.ipynb"
        path.write_text(json.dumps(nb), encoding="utf-8")
        return path

    def test_markdown_and_code_cells(self):
        text = ingot.notebook_to_text(self.make_notebook())
        self.assertIn("# %% [markdown] cell 1", text)
        self.assertIn("# # Title", text)
        self.assertIn("# %% [code] cell 2", text)
        self.assertIn("print('hi')", text)

    def test_outputs_off_by_default(self):
        text = ingot.notebook_to_text(self.make_notebook())
        self.assertNotIn("# --- output ---", text)
        self.assertNotIn("AAAA", text)

    def test_outputs_included_without_images(self):
        text = ingot.notebook_to_text(self.make_notebook(), include_outputs=True)
        self.assertIn("# --- output ---", text)
        self.assertIn("# hi", text)
        self.assertNotIn("AAAA", text)

    def test_empty_cells_skipped(self):
        text = ingot.notebook_to_text(self.make_notebook())
        self.assertNotIn("cell 3", text)

    def test_invalid_json_returns_raw_text(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "broken.ipynb"
        path.write_text("not json", encoding="utf-8")
        self.assertEqual(ingot.notebook_to_text(path), "not json")


class OutputTests(unittest.TestCase):
    def test_build_tree(self):
        tree = ingot.build_tree(["src/app.py", "README.md"])
        self.assertIn("src/", tree)
        self.assertIn("app.py", tree)
        self.assertIn("README.md", tree)

    def test_safe_name(self):
        self.assertEqual(ingot.safe_name("my app/v2"), "my_app_v2")

    def test_run_job_local_creates_project_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "my-project"
            write(src, "main.py", "print('hello')\n")
            out = Path(tmp) / "output"
            result = ingot.run_job("local", str(src), {"output_dir": str(out), "log": lambda m: None})
            self.assertEqual(result["path"].parent.name, "my-project")
            self.assertTrue(result["path"].is_file())
            text = result["path"].read_text(encoding="utf-8")
            self.assertIn("FILE 1/1: main.py", text)
            self.assertIn("print('hello')", text)
            self.assertEqual(result["files"], 1)

    def test_run_job_missing_folder_raises(self):
        with self.assertRaises(ingot.IngotError):
            ingot.run_job("local", "/definitely/not/here", {"output_dir": tempfile.gettempdir(), "log": lambda m: None})


class SavedShortcutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        cfg = Path(self.tmp.name)
        patches = [mock.patch.object(ingot, "CONFIG_DIR", cfg),
                   mock.patch.object(ingot, "SAVED_FILE", cfg / "saved.json")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_saving_repo_remembers_account(self):
        store = ingot.load_store()
        ingot.add_saved(store, "hello", "github", "octocat/Hello-World")
        item = ingot.find_saved(store, "hello")
        self.assertEqual(item["account"], "octocat")
        self.assertIn("octocat", ingot.saved_accounts(store))
        self.assertIsNotNone(ingot.find_saved(store, "octocat"))  # account auto-saved

    def test_repos_grouped_by_account(self):
        store = ingot.load_store()
        ingot.add_saved(store, "hello", "github", "octocat/Hello-World")
        ingot.add_saved(store, "spoon", "github", "octocat/Spoon-Knife")
        ingot.add_saved(store, "other", "github", "someone/else")
        names = [r["name"] for r in ingot.repos_of(store, "octocat")]
        self.assertEqual(sorted(names), ["hello", "spoon"])

    def test_shortcuts_persist_to_disk(self):
        store = ingot.load_store()
        ingot.add_saved(store, "notes", "local", "/tmp/notes")
        again = ingot.load_store()
        self.assertIsNotNone(ingot.find_saved(again, "notes"))

    def test_saving_same_name_replaces(self):
        store = ingot.load_store()
        ingot.add_saved(store, "x", "local", "/a")
        ingot.add_saved(store, "x", "local", "/b")
        self.assertEqual(len([i for i in store["items"] if i["name"] == "x"]), 1)
        self.assertEqual(ingot.find_saved(store, "x")["target"], "/b")


class WebHelperTests(unittest.TestCase):
    def test_split_csv(self):
        self.assertEqual(ingot_web.split_csv("py, js\nmd"), ["py", "js", "md"])

    def test_split_csv_empty(self):
        self.assertEqual(ingot_web.split_csv(""), [])
        self.assertEqual(ingot_web.split_csv(None), [])


if __name__ == "__main__":
    unittest.main()
