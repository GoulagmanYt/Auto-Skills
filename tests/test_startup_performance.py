"""Filesystem work budgets must not weaken repository containment."""

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from codex_bootstrap.fs import confined


class StartupFilesystemTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def test_deep_regular_paths_have_constant_canonicalization_budget(self):
        relative = "plugins/repomix/node_modules/@scope/library/dist/module/file.js"
        target = self.root / relative
        target.parent.mkdir(parents=True)
        target.write_text("content")
        original = Path.resolve
        calls = []

        def resolve(path, *args, **kwargs):
            calls.append(path)
            return original(path, *args, **kwargs)

        with patch.object(Path, "resolve", resolve):
            self.assertEqual(confined(self.root, relative), target)
        self.assertLessEqual(len(calls), 2)

    def test_unknown_reparse_points_keep_canonical_safety_check(self):
        original = Path.lstat
        alias = self.root / "redirected"
        alias.mkdir()
        outside = self.root.parent / "outside"
        original_resolve = Path.resolve

        def lstat(path, *args, **kwargs):
            if path == alias:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_reparse_tag=0x8000000A)
            return original(path, *args, **kwargs)

        def resolve(path, *args, **kwargs):
            if path == alias:
                return outside
            return original_resolve(path, *args, **kwargs)

        with patch.object(Path, "lstat", lstat), patch.object(Path, "resolve", resolve):
            with self.assertRaisesRegex(ValueError, "redirected"):
                confined(self.root, "redirected/file")

    def test_inside_and_outside_directory_aliases_are_both_rejected(self):
        from test_repository_boundaries import RepositoryBoundaryTests

        for name, target in (
            ("inside-link", self.root / "inside"),
            ("outside-link", self.root.parent),
        ):
            target.mkdir(exist_ok=True)
            link = self.root / name
            helper = RepositoryBoundaryTests()
            helper.make_alias(link, target)
            try:
                with self.assertRaisesRegex(ValueError, "redirected"):
                    confined(self.root, name + "/payload")
            finally:
                if link.is_symlink():
                    link.unlink()
                elif os.name == "nt":
                    link.rmdir()

    def test_initial_publication_verifies_the_complete_lock_once(self):
        from codex_bootstrap.bootstrap import bootstrap, verify_lock

        subprocess.run(["git", "init", "-q", str(self.root)], check=True, capture_output=True)
        (self.root / "README.md").write_text("# Manual")
        with patch("codex_bootstrap.bootstrap.verify_lock", wraps=verify_lock) as verify:
            lock = bootstrap(self.root, offline=True)
        self.assertEqual(verify.call_count, 1)
        self.assertEqual(verify_lock(self.root), lock)


if __name__ == "__main__":
    unittest.main()
