import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.check_public_tree import check_source


class PublicTreeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "src").mkdir()

    def test_personal_path_and_secret_are_rejected_without_echoing_values(self):
        target = self.root / "src/example.py"
        for text in ("/".join(["C:", "Users", "private", "repo"]), "sk-" + "x" * 30):
            target.write_text(text)
            with self.assertRaises(ValueError) as caught:
                check_source(self.root)
            self.assertNotIn(text, str(caught.exception))

    def test_local_state_is_ignored_before_git_but_rejected_if_tracked(self):
        (self.root / ".serena").mkdir()
        (self.root / ".serena/local.json").write_text("{}")
        (self.root / "src/example.py").write_text("pass")
        self.assertEqual(check_source(self.root), 1)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        with self.assertRaisesRegex(ValueError, "local/generated"):
            check_source(self.root)
