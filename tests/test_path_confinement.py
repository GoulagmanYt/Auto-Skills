import ntpath
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from suite_support import IsolatedTestCase

from codex_bootstrap.fs import confined


@unittest.skipUnless(sys.platform == "win32", "Windows path resolution race")
class WindowsConfinementTests(IsolatedTestCase):
    def test_parent_created_during_resolution_keeps_mutex_inside_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / ".codex/bootstrap.mutex"
            original = ntpath._getfinalpathname
            injected_errors = []

            def create_parent(path):
                try:
                    return original(path)
                except OSError as error:
                    if str(path) == str(target) and not target.parent.exists():
                        injected_errors.append(error.winerror)
                        target.parent.mkdir()
                    raise

            with patch.object(ntpath, "_getfinalpathname", side_effect=create_parent):
                self.assertEqual(confined(root, ".codex/bootstrap.mutex"), target)
            self.assertEqual(injected_errors, [3])

    def test_equivalent_extended_prefixes_compare_identically(self):
        from codex_bootstrap import fs

        normalize = getattr(fs, "_comparison_path", None)
        self.assertTrue(callable(normalize))
        for extended, ordinary in [
            (r"\\?\C:\repo\file", r"C:\repo\file"),
            (r"\\?\UNC\server\share\repo\file", r"\\server\share\repo\file"),
        ]:
            self.assertEqual(normalize(Path(extended)), Path(ordinary))
        volume = Path(r"\\?\Volume{example}\repo\file")
        self.assertEqual(normalize(volume), volume)

    def test_normalizing_prefix_does_not_accept_a_different_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / "file"
            target.touch()
            escaped = Path("\\\\?\\" + str(root.parent / (root.name + "-other") / "file"))
            original = Path.resolve

            def resolve(path, *args, **kwargs):
                return escaped if path == target else original(path, *args, **kwargs)

            with patch.object(Path, "resolve", resolve):
                with self.assertRaisesRegex(ValueError, "path escapes repository"):
                    confined(root, "file")


class PosixConfinementTests(IsolatedTestCase):
    @unittest.skipIf(os.name == "nt", "POSIX literal backslashes")
    def test_windows_prefix_is_not_interpreted_on_posix(self):
        from codex_bootstrap import fs

        path = Path(r"\\?\C:\repo\file")
        self.assertEqual(fs._comparison_path(path), path)
