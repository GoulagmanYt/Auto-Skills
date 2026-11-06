"""Integration evidence for scoped selection, immutable locks and native activation."""

import json
import os
import subprocess
import tempfile
import tomllib
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from codex_bootstrap.bootstrap import bootstrap, check, verify_lock
from codex_bootstrap.cli import requested_cwd
from codex_bootstrap.config import STATIC_HEADER, launch_overrides
from codex_bootstrap.proposal import propose
from codex_bootstrap.selection import Candidate
from codex_bootstrap.token_tools import install_token_tools


class ScopedInstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "repo"
        self.root.mkdir()
        for guard in (
            patch(
                "codex_bootstrap.inventory.allowed_repositories",
                return_value={"controlled-fixture/react-skills"},
            ),
            patch("codex_bootstrap.config.external_skills", return_value=set()),
            patch.dict(os.environ, {"CODEX_BOOTSTRAP_CACHE": str(self.root.parent / "test-cache")}),
        ):
            guard.start()
            self.addCleanup(guard.stop)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "package.json").write_text(
            '{"private":true,"workspaces":["apps/*"]}', encoding="utf-8"
        )
        self.package("apps/legacy", "^18.3.0")
        self.package("apps/current", "^19.0.0")

    def package(self, scope, version):
        directory = self.root / scope
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "package.json").write_text(
            json.dumps({"dependencies": {"react": version}}), encoding="utf-8"
        )

    @staticmethod
    def entry(lock, scope, slot="framework-react"):
        return next(
            entry
            for entry in lock["skills"]
            if entry.get("scope", ".") == scope and entry["slot"] == slot
        )

    @staticmethod
    def discovery(profile, github=None, *, slots=None, cache_dir=None, allowed_repositories=None):
        # Deliberately a controlled registry fixture, not a live GitHub discovery.
        candidates = [
            Candidate(
                slot="framework-react",
                name=f"external-react-{major}",
                body=(
                    f"---\nname: external-react-{major}\n"
                    "description: Review React rendering and component state.\n---\n"
                    "Read the nearest manifest. Check React component boundaries and state ownership. "
                    "Use bounded rendering tests to verify effects, updates and user interaction. "
                    "Avoid stale subscriptions; validate cleanup and measure affected behavior.\n"
                ),
                source="github",
                repository="controlled-fixture/react-skills",
                commit=str(major) * 20,
                remote_path=f"react-{major}/SKILL.md",
                compatibility={"react": f"^{major}.0.0"},
                technologies={"react"},
                license="MIT",
                stars=4321,
                updated=datetime.now(UTC).isoformat(),
            )
            for major in (18, 19)
        ]
        return candidates, {"queries": ["controlled fixture"], "errors": [], "rejected": []}

    def overrides(self, lock, cwd=None):
        with (
            patch("codex_bootstrap.config.external_skills", return_value=set()),
            patch("codex_bootstrap.config.config_layers", return_value=[]),
        ):
            args = launch_overrides(self.root, lock, cwd)
        return tomllib.loads("\n".join(args[1::2]))

    def test_external_version_specific_guides_are_selected_per_workspace(self):
        with patch("codex_bootstrap.proposal.discover", side_effect=self.discovery):
            report = propose(self.root)
        chosen = {
            entry["scope"]: entry
            for entry in report["selected"]
            if entry["slot"] == "framework-react"
        }
        self.assertEqual(set(chosen), {"apps/legacy", "apps/current"})
        self.assertEqual(chosen["apps/legacy"]["name"], "external-react-18")
        self.assertEqual(chosen["apps/current"]["name"], "external-react-19")
        self.assertTrue(all(entry["source"] == "github" for entry in chosen.values()))
        self.assertNotIn("react", report["workspaces"]["."]["technologies"])
        self.assertFalse((self.root / ".codex").exists())

    def test_shared_discovery_pool_cannot_mutate_previous_workspace_winners(self):
        guide = Candidate(
            slot="unit-testing",
            name="shared-javascript-tests",
            body=(
                "---\nname: javascript-tests\ndescription: Verify JavaScript behavior.\n---\n"
                "Read the nearest JavaScript package manifest. Use the existing test runner. "
                "Check observable behavior and error cases; verify state updates with bounded output."
            ),
            technologies={"javascript"},
            repository="controlled-fixture/testing-skills",
        )
        with patch(
            "codex_bootstrap.proposal.discover",
            return_value=([guide], {"queries": [], "errors": [], "rejected": []}),
        ):
            report = propose(self.root)
        selected = [entry for entry in report["selected"] if entry["slot"] == "unit-testing"]
        self.assertEqual(len(selected), 3)
        self.assertEqual(
            {entry["scope"] for entry in selected}, {".", "apps/legacy", "apps/current"}
        )

    def test_bootstrap_publishes_distinct_owned_paths_and_verifies_scoped_integrity(self):
        lock = bootstrap(self.root, offline=True)
        legacy = self.entry(lock, "apps/legacy")
        current = self.entry(lock, "apps/current")
        self.assertNotEqual(legacy["path"], current["path"])
        self.assertIn("@workspaces/apps/legacy/", legacy["path"])
        self.assertIn("@workspaces/apps/current/", current["discovery_path"])
        for entry in (legacy, current):
            self.assertEqual(
                (self.root / entry["path"]).read_bytes(),
                (self.root / entry["discovery_path"]).read_bytes(),
            )
        self.assertIn("^18.3.0", (self.root / legacy["path"]).read_text())
        self.assertIn("^19.0.0", (self.root / current["path"]).read_text())
        self.assertEqual(lock, verify_lock(self.root))
        self.assertEqual(check(self.root)["status"], "current")
        (self.root / current["path"]).write_text("untracked modification")
        with self.assertRaisesRegex(ValueError, "integrity failure"):
            verify_lock(self.root)

    def test_cd_workspace_enables_nearest_scope_and_disables_sibling_and_duplicate_guides(self):
        lock = bootstrap(self.root, offline=True)
        nested = self.root / "apps/current/src"
        nested.mkdir()
        cwd = requested_cwd(["-C", str(nested)])
        config = self.overrides(lock, cwd)
        enabled = {entry["path"]: entry["enabled"] for entry in config["skills"]["config"]}
        workspace_slots = {
            entry["slot"] for entry in lock["skills"] if entry.get("scope") == "apps/current"
        }
        for entry in lock["skills"]:
            scope = entry.get("scope", ".")
            expected = scope == "apps/current" or (
                scope == "." and entry["slot"] not in workspace_slots
            )
            for key in ("path", "discovery_path"):
                self.assertEqual(
                    enabled[str((self.root / entry[key]).resolve())],
                    expected and key == "discovery_path",
                )
        root_config = self.overrides(lock)
        root_enabled = {
            entry["path"]: entry["enabled"] for entry in root_config["skills"]["config"]
        }
        for entry in lock["skills"]:
            self.assertEqual(
                root_enabled[str((self.root / entry["discovery_path"]).resolve())],
                entry.get("scope", ".") == ".",
            )
        self.assertTrue(config["developer_instructions"].startswith(STATIC_HEADER))

    def test_each_active_skill_has_only_one_enabled_native_path(self):
        lock = bootstrap(self.root, offline=True)
        for cwd in (self.root, self.root / "apps/current"):
            config = self.overrides(lock, cwd)
            enabled = {e["path"] for e in config["skills"]["config"] if e["enabled"]}
            self.assertTrue(enabled)
            for entry in lock["skills"]:
                paths = {
                    str((self.root / entry[key]).resolve()) for key in ("path", "discovery_path")
                }
                self.assertLessEqual(len(enabled & paths), 1, entry["slot"])
            self.assertTrue(all("/.agents/skills/" in Path(p).as_posix() for p in enabled))

    def test_rust_child_inherits_only_portable_common_root_guides(self):
        self.package(".", "^19.0.0")
        (self.root / "src-tauri").mkdir()
        (self.root / "src-tauri/Cargo.toml").write_text(
            '[package]\nname="backend"\nversion="0.1.0"\n'
        )
        lock = bootstrap(self.root, offline=True)
        # A registry guide can specialize a common slot, too.
        security = self.entry(lock, ".", "security")
        security["technologies"] = ["react"]
        performance = self.entry(lock, ".", "performance")
        performance["compatibility"] = {"node": ">=20"}
        config = self.overrides(lock, self.root / "src-tauri")
        enabled = {e["path"] for e in config["skills"]["config"] if e["enabled"]}
        for slot in ("framework-react", "language-javascript", "security", "performance"):
            entry = self.entry(lock, ".", slot)
            for key in ("path", "discovery_path"):
                self.assertNotIn(str((self.root / entry[key]).resolve()), enabled, slot)
        for scope, slot in ((".", "architecture"), ("src-tauri", "language-rust")):
            entry = self.entry(lock, scope, slot)
            self.assertIn(str((self.root / entry["discovery_path"]).resolve()), enabled)

    def test_nested_workspace_activation_disables_parent_specialization(self):
        self.package("apps/current/embedded", "^18.3.0")
        lock = bootstrap(self.root, offline=True)
        config = self.overrides(lock, self.root / "apps/current/embedded")
        enabled = {entry["path"]: entry["enabled"] for entry in config["skills"]["config"]}
        child = self.entry(lock, "apps/current/embedded")
        parent = self.entry(lock, "apps/current")
        self.assertTrue(enabled[str((self.root / child["discovery_path"]).resolve())])
        self.assertFalse(enabled[str((self.root / parent["discovery_path"]).resolve())])

    def test_workspace_instructions_resolve_centralized_artifacts_after_static_header(self):
        lock = bootstrap(self.root, offline=True)
        config = self.overrides(lock, self.root / "apps/current")
        instructions = config["developer_instructions"]
        self.assertTrue(instructions.startswith(STATIC_HEADER))
        variable = instructions.removeprefix(STATIC_HEADER)
        self.assertTrue(str(self.root) in variable or self.root.as_posix() in variable)
        self.assertIn("apps/current", variable)
        self.assertIn("skills-lock.json", variable)
        self.assertIn("token-run", variable)

    def test_updating_one_workspace_preserves_sibling_files_metadata_and_lock_entry(self):
        before = bootstrap(self.root, offline=True)
        current_entry = self.entry(before, "apps/current")
        sibling = self.root / current_entry["path"]
        os.utime(sibling, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))
        sibling_state = (sibling.read_bytes(), sibling.stat().st_mtime_ns)
        self.package("apps/legacy", "^18.3.1")
        after = bootstrap(self.root, offline=True)
        self.assertEqual(self.entry(after, "apps/current"), current_entry)
        self.assertEqual((sibling.read_bytes(), sibling.stat().st_mtime_ns), sibling_state)
        key = "apps/current::framework-react"
        self.assertEqual(before["slot_inputs"][key], after["slot_inputs"][key])
        report = json.loads((self.root / ".codex/bootstrap-report.json").read_text())
        self.assertIn(key, report["changes"]["retained_slots"])
        self.assertNotIn(key, report["changes"]["refreshed_slots"])
        self.assertIn("^18.3.1", (self.root / self.entry(after, "apps/legacy")["path"]).read_text())
        self.assertEqual(after, verify_lock(self.root))

    def test_unrelated_refresh_preserves_external_source_quality_in_report(self):
        def offline_tools(stage, **options):
            return install_token_tools(stage, offline=True, enabled=options.get("enabled"))

        with (
            patch("codex_bootstrap.proposal.discover", side_effect=self.discovery),
            patch("codex_bootstrap.bootstrap.install_token_tools", side_effect=offline_tools),
        ):
            before = bootstrap(self.root)
        original = self.entry(before, "apps/current")
        self.assertEqual(original["source"], "github")
        self.assertEqual(original["quality"]["stars"], 4321)
        self.assertTrue(original["quality"]["repository_updated"])
        self.package("apps/legacy", "^18.3.1")
        after = bootstrap(self.root, offline=True)
        report = json.loads((self.root / ".codex/bootstrap-report.json").read_text())
        retained = next(
            entry
            for entry in report["selected"]
            if entry["scope"] == "apps/current" and entry["slot"] == "framework-react"
        )
        self.assertEqual(self.entry(after, "apps/current"), original)
        self.assertEqual(retained["quality"], original["quality"])
        self.assertEqual(retained["repository"], original["repository"])
        self.assertEqual(retained["commit"], original["commit"])

    def test_frontend_update_preserves_rust_workspace_and_tools(self):
        self.package(".", "^19.0.0")
        (self.root / "src-tauri").mkdir()
        (self.root / "src-tauri/Cargo.toml").write_text(
            '[package]\nname="backend"\nversion="0.1.0"\n'
        )
        before = bootstrap(self.root, offline=True)
        rust = [e for e in before["skills"] if e.get("scope") == "src-tauri"]
        paths = [self.root / e[k] for e in rust for k in ("path", "discovery_path")]
        paths += [self.root / ".codex/bin/token-run.py", self.root / ".codex/bin/repo-map.py"]
        for path in paths:
            os.utime(path, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))
        states = [(p.read_bytes(), p.stat().st_mtime_ns) for p in paths]
        self.package(".", "^19.1.0")
        with patch(
            "codex_bootstrap.token_tools.install_token_tools",
            side_effect=AssertionError("unexpected tool reinstall"),
        ):
            after = bootstrap(self.root, offline=True)
        self.assertEqual([e for e in after["skills"] if e.get("scope") == "src-tauri"], rust)
        self.assertEqual([(p.read_bytes(), p.stat().st_mtime_ns) for p in paths], states)
        report = json.loads((self.root / ".codex/bootstrap-report.json").read_text())
        self.assertFalse(report["changes"]["tools_reinstalled"])

    def test_removed_workspace_retires_only_its_owned_skill_files(self):
        before = bootstrap(self.root, offline=True)
        retired = [entry for entry in before["skills"] if entry.get("scope") == "apps/legacy"]
        (self.root / "apps/legacy/package.json").unlink()
        after = bootstrap(self.root, offline=True)
        self.assertNotIn("apps/legacy", {entry.get("scope") for entry in after["skills"]})
        for entry in retired:
            for key in ("path", "discovery_path"):
                self.assertFalse((self.root / entry[key]).exists())
                self.assertNotIn(entry[key], after["files"])
        self.assertEqual(self.entry(before, "apps/current"), self.entry(after, "apps/current"))
        self.assertEqual(after, verify_lock(self.root))


if __name__ == "__main__":
    unittest.main()
