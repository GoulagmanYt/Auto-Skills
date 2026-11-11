"""Manual declarations stay scoped, reviewable, and independent of source execution."""

import json
import subprocess
import tempfile
from pathlib import Path

from suite_support import IsolatedTestCase

from codex_bootstrap.profile import Profile


class RepositoryConfigurationTests(IsolatedTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def config(self, text):
        (self.root / "auto-skills.toml").write_text(text, encoding="utf-8")

    def test_missing_config_preserves_existing_profile(self):
        from codex_bootstrap.repo_config import apply_configuration, configured_scopes

        original = Profile(technologies={"python": ">=3.11"})
        self.assertEqual(configured_scopes(self.root), [])
        self.assertEqual(apply_configuration(self.root, {".": original})["."], original)

    def test_manual_values_precede_observations_without_erasing_them(self):
        from codex_bootstrap.repo_config import apply_configuration

        (self.root / "backend").mkdir()
        self.config(
            '[[workspaces]]\npath="backend"\nkind="application"\n'
            'technologies={cpp="20",cmake=">=3.22"}\nslots=["language-cpp"]\n'
        )
        original = Profile(
            technologies={"cpp": "17"},
            technology_sources={
                "cpp": [{"kind": "declaration", "path": "CMakeLists.txt", "version": "17"}]
            },
        )
        profile = apply_configuration(self.root, {"backend": original})["backend"]
        self.assertEqual(profile.technologies["cpp"], "20")
        self.assertEqual(original.technologies["cpp"], "17")
        self.assertEqual(profile.technology_sources["cpp"][0]["kind"], "manual")
        self.assertEqual(profile.technology_sources["cpp"][1]["version"], "17")
        self.assertIn("language-cpp", profile.slots)
        self.assertEqual(profile.repository_kind, "application")
        self.assertTrue(any("conflict" in warning for warning in profile.warnings))

    def test_root_kind_and_explicit_unknown_have_manual_provenance(self):
        from codex_bootstrap.repo_config import apply_configuration, read_configuration

        self.config('schema_version=1\n[repository]\nkind="unknown"\n')
        self.assertEqual(read_configuration(self.root)["repository"]["kind"], "unknown")
        profile = apply_configuration(self.root, {".": Profile()})["."]
        self.assertEqual(profile.repository_kind, "unknown")
        self.assertEqual(profile.kind_source["kind"], "manual")

    def test_manual_version_controls_selection_despite_conflicting_manifest_and_lock(self):
        from codex_bootstrap.catalog import bundled_candidates
        from codex_bootstrap.repo_config import apply_configuration
        from codex_bootstrap.selection import Candidate, rejection

        self.config('[[workspaces]]\npath="."\ntechnologies={react="^19"}\n')
        profile = Profile(
            technologies={"react": "^18"},
            slots=["framework-react"],
            resolved_versions={"react": ["18.3.1"]},
            technology_sources={
                "react": [{"kind": "declaration", "version": "^18", "path": "package.json"}]
            },
        )
        profile = apply_configuration(self.root, {".": profile})["."]
        body = bundled_candidates(profile)[0].body
        desired = Candidate(
            slot="framework-react",
            name="react-current",
            body=body,
            source="bundled",
            compatibility={"react": "^19"},
        )
        stale = Candidate(
            slot="framework-react",
            name="react-stale",
            body=body,
            source="bundled",
            compatibility={"react": "^18"},
        )
        self.assertIsNone(rejection(desired, profile))
        self.assertIsNotNone(rejection(stale, profile))
        self.assertEqual(profile.resolved_versions["react"], ["18.3.1"])

    def test_unknown_manual_technology_reports_missing_specialized_capability(self):
        from codex_bootstrap.repo_config import apply_configuration

        self.config('[[workspaces]]\npath="."\ntechnologies={niche_runtime="2"}\n')
        profile = apply_configuration(self.root, {".": Profile()})["."]
        self.assertEqual(profile.technologies["niche_runtime"], "2")
        self.assertTrue(
            any("specialized support is unknown" in warning for warning in profile.warnings)
        )

    def test_primary_proposal_report_shows_root_override_and_scoped_conflict_warnings(self):
        from codex_bootstrap.proposal import markdown_report, propose

        (self.root / "package.json").write_text('{"dependencies":{"react":"^18"}}')
        self.config('[[workspaces]]\npath="."\ntechnologies={react="^19"}\n')
        report = propose(self.root, offline=True)
        self.assertEqual(report["profile"]["technologies"]["react"], "^19")
        self.assertIn("declaration conflict", markdown_report(report))

    def test_invalid_configuration_fails_proposal_and_bootstrap_before_writes(self):
        from codex_bootstrap.bootstrap import bootstrap
        from codex_bootstrap.proposal import propose

        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        self.config('[[workspaces]]\npath="../outside"\n')
        for operation in (propose, bootstrap):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(ValueError, "auto-skills.toml"):
                    operation(self.root, offline=True)
                self.assertFalse((self.root / ".codex").exists())

    def test_root_documentation_and_manual_application_workspace_keep_separate_policies(self):
        from codex_bootstrap.proposal import propose

        (self.root / "README.md").write_text("# Handbook")
        (self.root / "backend").mkdir()
        self.config(
            '[repository]\nkind="documentation"\n[[workspaces]]\npath="backend"\n'
            'kind="application"\ntechnologies={cpp="20"}\n'
        )
        report = propose(self.root, offline=True)
        self.assertEqual(report["policy"]["effective"], "documentation")
        self.assertEqual(report["policy"]["scope_policies"]["backend"]["effective"], "complete")
        self.assertIn("language-cpp", report["workspaces"]["backend"]["slots"])
        self.assertIn("rtk", [tool["name"] for tool in report["tool_plan"]])

    def test_explicit_functional_slot_is_preserved_in_child_workspace(self):
        from codex_bootstrap.workspaces import selection_profiles

        (self.root / "backend").mkdir()
        self.config('[[workspaces]]\npath="backend"\nkind="application"\nslots=["security"]\n')
        self.assertIn("security", selection_profiles(self.root)["backend"].slots)

    def test_documentation_workspace_keeps_its_own_documentation_entry(self):
        from codex_bootstrap.proposal import propose

        (self.root / "handbook").mkdir()
        (self.root / "handbook/README.md").write_text("# Handbook")
        self.config('[[workspaces]]\npath="handbook"\nkind="documentation"\n')
        report = propose(self.root, offline=True)
        entries = [entry for entry in report["selected"] if entry["scope"] == "handbook"]
        self.assertEqual([entry["slot"] for entry in entries], ["documentation"])

    def test_bootstrapped_documentation_workspace_excludes_root_react_on_launch(self):
        from codex_bootstrap.bootstrap import bootstrap
        from codex_bootstrap.config import active_scope, enabled_skills

        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "package.json").write_text('{"dependencies":{"react":"^19"}}')
        (self.root / "handbook").mkdir()
        (self.root / "handbook/README.md").write_text("# Handbook")
        self.config('[[workspaces]]\npath="handbook"\nkind="documentation"\n')
        lock = bootstrap(self.root, offline=True)
        self.assertTrue(any(entry["slot"] == "framework-react" for entry in lock["skills"]))
        scope = active_scope(self.root, lock, self.root / "handbook")
        self.assertEqual(scope, "handbook")
        active = enabled_skills(lock, scope)
        self.assertFalse(any(entry["slot"] == "framework-react" for entry in active))
        self.assertTrue(
            any(
                entry["slot"] == "documentation" and entry["scope"] == "handbook"
                for entry in active
            )
        )

    def test_invalid_config_rejected_without_mutation(self):
        from codex_bootstrap.repo_config import read_configuration

        invalid = [
            "schema_version=2",
            '[repository]\nkind="service"',
            '[[workspaces]]\npath="../outside"',
            '[[workspaces]]\npath="C:/outside"',
            '[[workspaces]]\npath="missing"',
            '[[workspaces]]\npath="node_modules"',
            '[[workspaces]]\npath="."\nslots=["arbitrary-role"]',
            '[[workspaces]]\npath="."\ntechnologies={python="https://secret@example.com"}',
            '[[workspaces]]\npath="."\ntechnologies={"../secret"="1"}',
            '[repository]\ncommand="execute this"',
            "schema_version=true",
        ]
        (self.root / "node_modules").mkdir()
        for text in invalid:
            with self.subTest(text=text):
                self.config(text)
                before = sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*"))
                with self.assertRaisesRegex(ValueError, "auto-skills.toml"):
                    read_configuration(self.root)
                self.assertEqual(
                    before,
                    sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*")),
                )

    def test_duplicate_scopes_and_submodule_paths_rejected(self):
        from codex_bootstrap.repo_config import configured_scopes

        (self.root / "nested").mkdir()
        (self.root / "nested/.git").write_text("gitdir: ../.git/modules/nested")
        self.config('[[workspaces]]\npath="nested"\n')
        with self.assertRaises(ValueError):
            configured_scopes(self.root)
        self.config('[[workspaces]]\npath="."\n[[workspaces]]\npath="."\n')
        with self.assertRaises(ValueError):
            configured_scopes(self.root)

    def test_symlink_scope_and_config_are_rejected(self):
        from codex_bootstrap.repo_config import configured_scopes

        (self.root / "real").mkdir()
        try:
            (self.root / "linked").symlink_to(self.root / "real", target_is_directory=True)
        except OSError:
            self.skipTest("symlinks unavailable")
        self.config('[[workspaces]]\npath="linked"\n')
        with self.assertRaises(ValueError):
            configured_scopes(self.root)
        (self.root / "auto-skills.toml").unlink()
        (self.root / "settings.toml").write_text("schema_version=1")
        (self.root / "auto-skills.toml").symlink_to(self.root / "settings.toml")
        with self.assertRaises(ValueError):
            configured_scopes(self.root)

    def test_config_only_workspace_is_reported_without_writes(self):
        from codex_bootstrap.proposal import propose

        (self.root / "backend").mkdir()
        self.config(
            '[[workspaces]]\npath="backend"\nkind="application"\n'
            'technologies={cpp="20",cmake=">=3.22"}\n'
        )
        report = propose(self.root, offline=True)
        profile = report["workspaces"]["backend"]
        self.assertEqual(profile["technologies"]["cpp"], "20")
        self.assertEqual(profile["technology_sources"]["cpp"][0]["path"], "auto-skills.toml")
        self.assertFalse((self.root / ".codex").exists())

    def test_manual_change_refreshes_only_its_workspace_and_keeps_sibling_mtime(self):
        from codex_bootstrap.bootstrap import bootstrap, check

        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        for scope in ("first", "second"):
            (self.root / scope).mkdir()
            (self.root / scope / "package.json").write_text(
                json.dumps({"dependencies": {"react": "^19"}})
            )
        self.config('[[workspaces]]\npath="first"\ntechnologies={react="^19"}\n')
        first = bootstrap(self.root, offline=True)
        entry = next(
            item
            for item in first["skills"]
            if item.get("scope") == "second" and item["slot"] == "framework-react"
        )
        sibling = self.root / entry["path"]
        timestamp = sibling.stat().st_mtime_ns
        self.config('[[workspaces]]\npath="first"\ntechnologies={react="^18"}\n')
        status = check(self.root)
        self.assertIn("auto-skills.toml", status["manifest_changes"])
        self.assertIn("first::framework-react", status["affected_slots"])
        self.assertFalse(any(slot.startswith("second::") for slot in status["affected_slots"]))
        bootstrap(self.root, offline=True)
        self.assertEqual(sibling.stat().st_mtime_ns, timestamp)
        self.assertEqual(check(self.root)["status"], "current")

    def test_invalid_refresh_preserves_published_lock_and_skill(self):
        from codex_bootstrap.bootstrap import bootstrap

        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "package.json").write_text('{"dependencies":{"react":"^19"}}')
        first = bootstrap(self.root, offline=True)
        lock_path = self.root / ".codex/skills-lock.json"
        skill = self.root / first["skills"][0]["path"]
        previous = (lock_path.read_bytes(), skill.read_bytes(), skill.stat().st_mtime_ns)
        self.config('[[workspaces]]\npath=".codex"\ntechnologies={cpp="20"}\n')
        with self.assertRaisesRegex(ValueError, "auto-skills.toml"):
            bootstrap(self.root, offline=True)
        self.assertEqual(
            (lock_path.read_bytes(), skill.read_bytes(), skill.stat().st_mtime_ns), previous
        )
