import json
import tempfile
import unittest
from pathlib import Path

from codex_bootstrap.profile import BASE_SLOTS, profile_repo
from codex_bootstrap.selection import Candidate, select
from codex_bootstrap.workspaces import selection_profiles, workspace_profiles, workspace_roots


class WorkspaceProfileTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def node(self, relative, version):
        self.write(relative, json.dumps({"dependencies": {"react": version}}))

    def test_simple_repository_preserves_profile(self):
        self.node("package.json", "^19.0")
        original = profile_repo(self.root)
        scopes = workspace_profiles(self.root, original)
        self.assertEqual(list(scopes), ["."])
        self.assertEqual(scopes["."].to_dict(), original.to_dict())
        self.assertIsNot(scopes["."], original)

    def test_independent_react_versions_and_python_are_not_mixed(self):
        self.write("package.json", '{"private":true,"workspaces":["apps/*"]}')
        self.node("apps/legacy/package.json", "^18.3.0")
        self.node("apps/current/package.json", "^19.0.0")
        self.write(
            "services/api/pyproject.toml",
            '[project]\nname="api"\nversion="0.1"\ndependencies=["fastapi>=0.115,<1"]',
        )
        profiles = workspace_profiles(self.root)
        self.assertEqual(set(profiles), {".", "apps/legacy", "apps/current", "services/api"})
        self.assertNotIn("react", profiles["."].technologies)
        self.assertEqual(profiles["apps/legacy"].technologies["react"], "^18.3.0")
        self.assertEqual(profiles["apps/current"].technologies["react"], "^19.0.0")
        self.assertNotIn("fastapi", profiles["apps/current"].technologies)
        self.assertIn("framework-fastapi", profiles["services/api"].slots)
        self.assertEqual(profiles["apps/current"].manifests, ["package.json"])

    def test_common_baseline_once_and_specialized_build_testing_per_workspace(self):
        self.node("apps/legacy/package.json", "^18")
        self.node("apps/current/package.json", "^19")
        selected = selection_profiles(self.root)
        self.assertTrue(set(BASE_SLOTS).issubset(selected["."].slots))
        for scope in ("apps/legacy", "apps/current"):
            self.assertIn("framework-react", selected[scope].slots)
            self.assertIn("unit-testing", selected[scope].slots)
            self.assertIn("build", selected[scope].slots)
            self.assertNotIn("token-output-compression", selected[scope].slots)
            self.assertNotIn("architecture", selected[scope].slots)

    def test_selector_can_choose_distinct_react_guides_for_sibling_workspaces(self):
        self.node("apps/legacy/package.json", "^18.3.0")
        self.node("apps/current/package.json", "^19.0.0")
        profiles = selection_profiles(self.root)
        guides = [
            Candidate(
                slot="framework-react",
                name=f"react-{major}",
                body=(
                    "---\nname: react-guide\ndescription: Review React component changes.\n---\n"
                    "Inspect the React component boundary and preserve existing state ownership. "
                    "Exercise rendering and affected user interactions using the existing test runner."
                ),
                repository="fixture/skills",
                compatibility={"react": f"^{major}.0.0"},
            )
            for major in (18, 19)
        ]
        for scope, expected in (("apps/legacy", "react-18"), ("apps/current", "react-19")):
            winners, rejected = select(guides, profiles[scope])
            self.assertEqual([winner.name for winner in winners], [expected])
            self.assertEqual(len(rejected), 1)
            self.assertIn("incompatible", rejected[0]["reason"])

    def test_inherits_runtime_pin_without_overwriting_child_constraint(self):
        self.write(".nvmrc", "22.11.0")
        self.node("apps/legacy/package.json", "^18")
        self.write(
            "apps/current/package.json",
            '{"engines":{"node":">=20"},"dependencies":{"react":"^19"}}',
        )
        profiles = workspace_profiles(self.root)
        self.assertEqual(profiles["apps/legacy"].technologies["node"], "22.11.0")
        self.assertEqual(profiles["apps/current"].technologies["node"], ">=20")
        self.assertEqual(profiles["apps/legacy"].resolved_versions["node"], ["22.11.0"])
        self.assertNotIn("react", profiles["."].technologies)

    def test_cargo_members_and_nested_scopes_keep_nearest_ownership(self):
        self.write("Cargo.toml", '[workspace]\nmembers=["crates/*"]')
        self.write("crates/a/Cargo.toml", '[package]\nname="a"\nversion="0.1.0"')
        self.write("crates/b/Cargo.toml", '[package]\nname="b"\nversion="0.1.0"')
        self.node("crates/a/ui/package.json", "^19")
        profiles = workspace_profiles(self.root)
        self.assertEqual(set(profiles), {".", "crates/a", "crates/a/ui", "crates/b"})
        self.assertNotIn("react", profiles["crates/a"].technologies)
        self.assertEqual(profiles["crates/a/ui"].technologies["react"], "^19")
        self.assertEqual(profiles["crates/a"].manifests, ["Cargo.toml"])

    def test_runtime_pins_are_inherited_only_by_workspaces_using_that_runtime(self):
        self.write(".nvmrc", "22.11.0")
        self.write(".python-version", "3.12.8")
        self.node("web/package.json", "^19")
        self.write("backend/Cargo.toml", '[package]\nname="backend"\nversion="0.1.0"')
        profiles = workspace_profiles(self.root)
        self.assertEqual(profiles["web"].technologies["node"], "22.11.0")
        self.assertNotIn("python", profiles["web"].technologies)
        self.assertNotIn("node", profiles["backend"].technologies)
        self.assertNotIn("python", profiles["backend"].technologies)

    def test_runtime_pin_crosses_an_unrelated_parent_without_polluting_it(self):
        self.write(".nvmrc", "22.11.0")
        self.write("backend/Cargo.toml", '[package]\nname="backend"\nversion="0.1.0"')
        self.node("backend/ui/package.json", "^19")
        self.write("backend/ui/nested/package.json", '{"dependencies":{"react":"^18"}}')
        profiles = workspace_profiles(self.root)
        self.assertNotIn("node", profiles["backend"].technologies)
        for scope in ("backend/ui", "backend/ui/nested"):
            self.assertEqual(profiles[scope].technologies["node"], "22.11.0")
            source = profiles[scope].technology_sources["node"][0]
            self.assertEqual(source["inherited_from"], ".")

    def test_generated_and_symlink_paths_cannot_create_workspaces(self):
        self.node("node_modules/a/package.json", "^18")
        self.node(".codex/skills/a/package.json", "^18")
        self.node("apps/valid/package.json", "^19")
        self.assertEqual(workspace_roots(self.root), [".", "apps/valid"])
        with tempfile.TemporaryDirectory() as other:
            foreign = Path(other)
            (foreign / "package.json").write_text('{"dependencies":{"react":"^18"}}')
            try:
                (self.root / "escape").symlink_to(foreign, target_is_directory=True)
            except OSError:
                return
            self.assertEqual(workspace_roots(self.root), [".", "apps/valid"])


if __name__ == "__main__":
    unittest.main()
