import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from suite_support import IsolatedTestCase

from codex_bootstrap.bootstrap import bootstrap, recover_transaction, verify_lock
from codex_bootstrap.cli import main
from codex_bootstrap.fs import digest


class LifecycleUpgradeTests(IsolatedTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def package(self, **dependencies):
        (self.root / "package.json").write_text(json.dumps({"dependencies": dependencies}))

    def test_offline_propose_does_not_create_repository_configuration(self):
        from codex_bootstrap.proposal import propose

        self.package(react="^19", typescript="^5")
        report = propose(self.root, offline=True)
        self.assertEqual(report["mode"], "proposal")
        self.assertEqual(
            len({entry["slot"] for entry in report["selected"]}), len(report["selected"])
        )
        self.assertFalse((self.root / ".codex").exists())
        self.assertFalse((self.root / "AGENTS.md").exists())
        self.assertFalse((self.root / ".agents").exists())

    def test_proposal_refuses_a_cache_inside_target_before_any_write(self):
        from codex_bootstrap.proposal import propose

        self.package(react="^19")
        with self.assertRaisesRegex(ValueError, "cache.*outside"):
            propose(self.root, cache_dir=self.root / ".codex/cache")
        self.assertFalse((self.root / ".codex").exists())

    def test_slot_inputs_preserve_actual_workspace_declarations(self):
        from codex_bootstrap.lifecycle import slot_inputs
        from codex_bootstrap.profile import Profile

        p = Profile(
            technologies={"react": "multiple"},
            slots=["framework-react"],
            technology_sources={
                "react": [
                    {"path": "one/package.json", "version": "^18"},
                    {"path": "two/package.json", "version": "^19"},
                ]
            },
        )
        original = json.dumps(slot_inputs(p, "framework-react"), sort_keys=True)
        p.technology_sources["react"][0]["version"] = "^17"
        self.assertNotEqual(original, json.dumps(slot_inputs(p, "framework-react"), sort_keys=True))

    def test_cli_dry_run_never_calls_installer(self):
        self.package(react="^19")
        import contextlib
        import io

        with (
            contextlib.redirect_stdout(io.StringIO()),
            patch("codex_bootstrap.cli.bootstrap", side_effect=AssertionError("must not install")),
        ):
            self.assertEqual(
                main(["bootstrap", "--repo", str(self.root), "--dry-run", "--offline"]), 0
            )
        self.assertFalse((self.root / ".codex").exists())

    def test_manifest_change_refreshes_without_reinstalling_tools_or_unrelated_skills(self):
        self.package(react="^19", typescript="^5")
        first = bootstrap(self.root, offline=True)
        rust = self.root / "Cargo.toml"
        rust.write_text('[package]\nname="fixture"\nversion="1.0.0"\nedition="2021"\n')
        tool = self.root / ".codex/bin/token-run.py"
        token_skill = self.root / ".codex/skills/token-context-pruning/SKILL.md"
        before = (tool.stat().st_mtime_ns, token_skill.stat().st_mtime_ns)
        with patch(
            "codex_bootstrap.token_tools.install_token_tools",
            side_effect=AssertionError("tool reinstall"),
        ):
            second = bootstrap(self.root, offline=True)
        self.assertIn("language-rust", {s["slot"] for s in second["skills"]})
        self.assertEqual(before, (tool.stat().st_mtime_ns, token_skill.stat().st_mtime_ns))
        self.assertNotEqual(first["manifest_hashes"], second["manifest_hashes"])
        self.assertEqual(second, verify_lock(self.root))
        self.assertEqual(second, bootstrap(self.root, offline=True))

    def test_removed_slot_is_removed_from_both_skill_locations(self):
        self.package(react="^19")
        bootstrap(self.root, offline=True)
        self.package()
        second = bootstrap(self.root, offline=True)
        self.assertNotIn("framework-react", {s["slot"] for s in second["skills"]})
        self.assertFalse((self.root / ".codex/skills/framework-react/SKILL.md").exists())
        self.assertFalse((self.root / ".agents/skills/framework-react/SKILL.md").exists())

    def test_corrupt_skill_is_never_silently_repaired_during_refresh(self):
        self.package(react="^19")
        bootstrap(self.root, offline=True)
        (self.root / ".codex/skills/framework-react/SKILL.md").write_text("manual edit")
        self.package(react="^20")
        with self.assertRaisesRegex(ValueError, "integrity"):
            bootstrap(self.root, offline=True)

    def test_failed_refresh_publication_rolls_back_and_next_launch_recovers(self):
        import codex_bootstrap.transaction as transaction

        self.package(react="^19")
        first = bootstrap(self.root, offline=True)
        lock_path = self.root / ".codex/skills-lock.json"
        before = lock_path.read_bytes()
        self.package(react="^19", typescript="^5")
        actual_write = transaction.atomic_write
        writes = 0

        def fail_once(path, data, **kwargs):
            nonlocal writes
            if "/skills/" in path.as_posix():
                writes += 1
                if writes == 3:
                    raise OSError("simulated interrupted disk write")
            return actual_write(path, data, **kwargs)

        with patch.object(transaction, "atomic_write", side_effect=fail_once):
            with self.assertRaisesRegex(OSError, "simulated"):
                bootstrap(self.root, offline=True)
        self.assertEqual(before, lock_path.read_bytes())
        self.assertEqual(first, verify_lock(self.root))
        self.assertFalse((self.root / ".codex/bootstrap-journal.json").exists())
        second = bootstrap(self.root, offline=True)
        self.assertIn("language-typescript", {entry["slot"] for entry in second["skills"]})

    def test_interrupted_refresh_restores_old_files_and_old_lock(self):
        import base64
        import hashlib

        self.package(react="^19")
        first = bootstrap(self.root, offline=True)
        lock_path = self.root / ".codex/skills-lock.json"
        old_lock = lock_path.read_bytes()
        skill_path = first["skills"][0]["path"]
        skill = self.root / skill_path
        before = skill.read_bytes()
        skill.write_text("interrupted new skill")
        journal = {
            "schema_version": 2,
            "previous_lock": base64.b64encode(old_lock).decode(),
            "new_lock_sha256": hashlib.sha256(b"never-published").hexdigest(),
            "files": {
                skill_path: {
                    "before": base64.b64encode(before).decode(),
                    "after": digest(skill),
                    "mode": 0o644,
                }
            },
        }
        (self.root / ".codex/bootstrap-journal.json").write_text(json.dumps(journal))
        recover_transaction(self.root)
        self.assertEqual(skill.read_bytes(), before)
        self.assertEqual(lock_path.read_bytes(), old_lock)
        self.assertEqual(first, verify_lock(self.root))


if __name__ == "__main__":
    unittest.main()
