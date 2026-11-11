import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from suite_support import IsolatedTestCase

from codex_bootstrap.bootstrap import bootstrap, check
from codex_bootstrap.cli import requested_cwd
from codex_bootstrap.proposal import propose


class PolicyTests(IsolatedTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def test_documentation_does_not_plan_node_or_rtk(self):
        (self.root / "README.md").write_text("# Manual\n")
        report = propose(self.root, offline=True)
        self.assertEqual(report["policy"]["effective"], "documentation")
        self.assertEqual(len(report["selected"]), 6)
        self.assertEqual([t["name"] for t in report["tool_plan"]], ["token-run", "repo-map"])
        lock = bootstrap(self.root, offline=True)
        self.assertEqual({t["name"] for t in lock["tools"]}, {"token-run", "repo-map"})

    def test_python_and_javascript_have_different_export_tools(self):
        (self.root / "pyproject.toml").write_text('[project]\nname="api"\nversion="1"\n')
        python = propose(self.root, offline=True)
        self.assertNotIn("repomix", {t["name"] for t in python["tool_plan"]})
        (self.root / "package.json").write_text(json.dumps({"dependencies": {"react": "^19"}}))
        js = propose(self.root, offline=True)
        self.assertIn("repomix", {t["name"] for t in js["tool_plan"]})

    def test_documentation_to_application_refresh_updates_tools(self):
        (self.root / "README.md").write_text("# Manual\n")
        first = bootstrap(self.root, offline=True)
        (self.root / "package.json").write_text(json.dumps({"dependencies": {"react": "^19"}}))
        self.assertEqual(check(self.root)["status"], "stale")
        second = bootstrap(self.root, offline=True)
        self.assertGreater(len(second["skills"]), len(first["skills"]))
        self.assertIn("repomix", {t["name"] for t in second["tools"]})
        self.assertEqual(check(self.root)["status"], "current")

    def test_explicit_preset_persists_on_next_launch(self):
        (self.root / "README.md").write_text("# Manual\n")
        first = bootstrap(self.root, offline=True, preset="complete")
        self.assertGreaterEqual(len(first["skills"]), 13)
        self.assertEqual(first, bootstrap(self.root, offline=True))
        self.assertEqual(check(self.root)["status"], "current")
        self.assertEqual(check(self.root, preset="documentation")["status"], "stale")

    def test_attached_cd_argument_activates_the_same_workspace_as_codex(self):
        target = self.root / "apps/modern"
        for args in (["-C" + str(target)], ["-C=" + str(target)], ["--cd=" + str(target)]):
            self.assertEqual(requested_cwd(args), target.resolve())

    def test_documentation_generator_dependencies_do_not_make_an_application(self):
        (self.root / "README.md").write_text("# Manual\n")
        (self.root / "mkdocs.yml").write_text("site_name: Manual\n")
        (self.root / "requirements.txt").write_text("mkdocs==1.6.1\nmkdocs-material==9.5.0\n")
        report = propose(self.root, offline=True)
        self.assertEqual(report["policy"]["effective"], "documentation")
        self.assertEqual(len(report["selected"]), 6)
        (self.root / "package.json").write_text(
            json.dumps(
                {
                    "dependencies": {
                        "@docusaurus/core": "3.9.0",
                        "react": "^19.0",
                        "react-dom": "^19.0",
                    }
                }
            )
        )
        self.assertEqual(propose(self.root, offline=True)["policy"]["effective"], "documentation")
        (self.root / "api").mkdir()
        (self.root / "api/pyproject.toml").write_text(
            '[project]\nname="api"\ndependencies=["fastapi>=0.115"]\n'
        )
        self.assertEqual(propose(self.root, offline=True)["policy"]["effective"], "complete")


if __name__ == "__main__":
    unittest.main()
