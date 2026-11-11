import tempfile
from pathlib import Path

from suite_support import IsolatedTestCase

from codex_bootstrap.policy import policy_for, tool_plan
from codex_bootstrap.profile import profile_repo


class UnknownRepositoryTests(IsolatedTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def test_readme_does_not_make_unsupported_source_documentary(self):
        self.write("README.md", "# Custom application")
        self.write("src/main.customlang", "unrecognized implementation")
        profile = profile_repo(self.root)
        policy = policy_for(self.root, profile)
        self.assertEqual(policy["repository_kind"], "unknown")
        self.assertEqual(policy["effective"], "unknown")
        self.assertIn("src/main.customlang", policy["unrecognized_evidence"])
        self.assertEqual([t["name"] for t in tool_plan(profile, policy)], ["token-run", "repo-map"])

    def test_empty_repo_is_unknown_and_documentation_only_remains_documentary(self):
        self.assertEqual(
            policy_for(self.root, profile_repo(self.root))["repository_kind"], "unknown"
        )
        self.write("README.md", "# User manual")
        self.write("docs/guide.md", "# Guide")
        policy = policy_for(self.root, profile_repo(self.root))
        self.assertEqual(policy["repository_kind"], "documentation")
        self.assertEqual(policy["effective"], "documentation")

    def test_unknown_project_does_not_read_source_contents(self):
        self.write("README.md", "# App")
        self.write("src/private.customlang", "content must not be read")
        from unittest.mock import patch

        original = Path.read_text

        def guarded(path, *args, **kwargs):
            if path.suffix == ".customlang":
                raise AssertionError("source read")
            return original(path, *args, **kwargs)

        with patch.object(Path, "read_text", guarded):
            policy = policy_for(self.root, profile_repo(self.root))
        self.assertEqual(policy["repository_kind"], "unknown")

    def test_bounded_inspection_reports_omissions(self):
        from codex_bootstrap.repo_inspection import inspect_repository

        self.write("README.md", "# App")
        self.write("nested/deep/main.customlang", "implementation")
        result = inspect_repository(self.root, max_depth=0)
        self.assertTrue(result["incomplete"])
        self.assertTrue(any(d["code"] == "depth_limit" for d in result["diagnostics"]))

    def test_agent_instructions_alone_do_not_establish_documentation_repo(self):
        self.write("AGENTS.md", "# Repository instructions")
        policy = policy_for(self.root, profile_repo(self.root))
        self.assertEqual(policy["repository_kind"], "unknown")

    def test_manual_only_javascript_plans_its_tools(self):
        self.write(
            "auto-skills.toml",
            'schema_version=1\n[[workspaces]]\npath="."\ntechnologies={react="^19"}\n',
        )
        policy = policy_for(self.root, profile_repo(self.root))
        self.assertIn("repomix", {t["name"] for t in tool_plan(profile_repo(self.root), policy)})

    def test_explicit_unknown_mode_keeps_portable_guides_and_explicit_roles_only(self):
        from codex_bootstrap.proposal import propose

        self.write("package.json", '{"dependencies":{"react":"^19"}}')
        self.write("auto-skills.toml", '[repository]\nkind="unknown"\n')
        report = propose(self.root, offline=True)
        self.assertEqual(report["policy"]["repository_kind"], "unknown")
        self.assertNotIn("framework-react", {s["slot"] for s in report["selected"]})
        self.assertEqual([t["name"] for t in report["tool_plan"]], ["token-run", "repo-map"])
        self.write(
            "auto-skills.toml",
            '[repository]\nkind="unknown"\n[[workspaces]]\npath="."\nslots=["framework-react"]\n',
        )
        explicit = propose(self.root, offline=True)
        self.assertIn("framework-react", {s["slot"] for s in explicit["selected"]})
