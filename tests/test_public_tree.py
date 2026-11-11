import subprocess
import tempfile
from pathlib import Path

from suite_support import IsolatedTestCase

from tools.check_public_tree import check_source


class PublicTreeTests(IsolatedTestCase):
    def test_force_staged_private_paths_are_rejected(self):
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        for relative in (
            "reports/private/session.json",
            "reports/PRIVATE/session.json",
            "reports/benchmarks/raw/transcript.json",
            "docs/superpowers/plans/internal.md",
            "dist-ci/package.txt",
        ):
            with self.subTest(relative=relative):
                target = self.root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("synthetic private note")
                subprocess.run(["git", "-C", str(self.root), "add", "-f", relative], check=True)
                with self.assertRaisesRegex(ValueError, "local/generated"):
                    check_source(self.root)
                subprocess.run(
                    ["git", "-C", str(self.root), "rm", "--cached", relative],
                    check=True,
                    capture_output=True,
                )
                target.unlink()

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
