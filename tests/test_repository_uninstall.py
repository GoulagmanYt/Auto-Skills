import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from suite_support import IsolatedTestCase

from codex_bootstrap.bootstrap import bootstrap


class RepositoryUninstallTests(IsolatedTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def uninstall(self, **kwargs):
        from codex_bootstrap.repository_uninstall import uninstall_repository

        return uninstall_repository(self.root, **kwargs)

    def test_original_bytes_survive_refresh_and_repository_uninstall(self):
        originals = {
            "AGENTS.md": b"# mine\r\n\r\n",
            ".codexignore": b"private-user-dir/\r\n\r\n",
            ".codex/config.toml": b'# mine\r\nmodel = "user-choice"\r\n',
        }
        for relative, content in originals.items():
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        bootstrap(self.root, offline=True)
        bootstrap(self.root, offline=True, refresh_all=True)
        result = self.uninstall()
        self.assertFalse(result["conflicts"])
        for relative, content in originals.items():
            self.assertEqual((self.root / relative).read_bytes(), content)
        self.assertFalse((self.root / ".codex/skills-lock.json").exists())
        self.assertEqual(self.uninstall()["status"], "not-installed")

    def test_user_edits_after_managed_blocks_are_preserved(self):
        (self.root / "AGENTS.md").write_bytes(b"# user\r\n")
        (self.root / ".codexignore").write_bytes(b"user-dir/\r\n")
        bootstrap(self.root, offline=True)
        for relative in ("AGENTS.md", ".codexignore"):
            with (self.root / relative).open("ab") as stream:
                stream.write(b"\n# appended by user\r\n")
        self.assertFalse(self.uninstall()["conflicts"])
        self.assertEqual(
            (self.root / "AGENTS.md").read_bytes(), b"# user\r\n\n# appended by user\r\n"
        )
        self.assertEqual(
            (self.root / ".codexignore").read_bytes(), b"user-dir/\r\n\n# appended by user\r\n"
        )

    def test_conflict_aborts_before_any_artifact_is_deleted(self):
        lock = bootstrap(self.root, offline=True)
        skill = self.root / lock["skills"][0]["path"]
        skill.write_text("user edits")
        result = self.uninstall()
        self.assertTrue(result["conflicts"])
        self.assertTrue((self.root / ".codex/skills-lock.json").exists())
        self.assertTrue((self.root / ".codex/bin/token-run.py").exists())
        self.assertEqual(skill.read_text(), "user edits")

    def test_dry_run_preserves_files_and_unknown_files_survive_uninstall(self):
        bootstrap(self.root, offline=True)
        personal = self.root / ".codex/personal.txt"
        personal.write_text("mine")
        before = (self.root / "AGENTS.md").read_bytes()
        result = self.uninstall(dry_run=True)
        self.assertFalse(result["conflicts"])
        self.assertEqual((self.root / "AGENTS.md").read_bytes(), before)
        self.uninstall()
        self.assertEqual(personal.read_text(), "mine")

    def test_tampered_lock_cannot_delete_user_paths(self):
        bootstrap(self.root, offline=True)
        path = self.root / ".codex/skills-lock.json"
        lock = json.loads(path.read_text())
        lock["files"]["README.md"] = "bad"
        path.write_text(json.dumps(lock))
        with self.assertRaisesRegex(ValueError, "unowned"):
            self.uninstall()

    def test_existing_backup_is_never_overwritten_by_a_new_bootstrap(self):
        backup = self.root / ".codex/original-state.json"
        backup.parent.mkdir()
        backup.write_bytes(b"user backup retained after a missing lock")
        with self.assertRaisesRegex(ValueError, "backup"):
            bootstrap(self.root, offline=True)
        self.assertEqual(backup.read_bytes(), b"user backup retained after a missing lock")

    def test_context_cli_explains_uninitialized_repository_without_writing(self):
        import io
        from contextlib import redirect_stderr

        from codex_bootstrap.cli import main

        error = io.StringIO()
        with redirect_stderr(error):
            code = main(["context", "--repo", str(self.root), "--json"])
        self.assertEqual(code, 1)
        self.assertIn("not initialized", error.getvalue())
        self.assertFalse((self.root / ".codex").exists())

    def test_legacy_empty_agents_file_is_preserved_without_inventing_absence(self):
        lock = bootstrap(self.root, offline=True)
        path = self.root / ".codex/skills-lock.json"
        del lock["files"][".codex/original-state.json"]
        path.write_text(json.dumps(lock))
        result = self.uninstall()
        self.assertFalse(result["conflicts"])
        self.assertTrue((self.root / "AGENTS.md").exists())
        self.assertEqual((self.root / "AGENTS.md").read_bytes(), b"")


if __name__ == "__main__":
    unittest.main()
