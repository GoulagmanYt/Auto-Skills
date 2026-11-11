import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from suite_support import IsolatedTestCase


class SimulatedRepositoryTests(IsolatedTestCase):
    def test_supported_stacks_and_known_gaps_are_reported_faithfully(self):
        from tools.repo_scenarios import SCENARIOS
        from tools.simulate_repositories import assess_scenario

        with tempfile.TemporaryDirectory(prefix="auto-skills-matrix-test-") as directory:
            for scenario in SCENARIOS:
                with self.subTest(repository=scenario.slug):
                    result, report = assess_scenario(scenario, Path(directory) / scenario.slug)
                    self.assertFalse(set(result["missing_slots"]) - set(scenario.known_gaps))
                    self.assertEqual(result["unexpected_slots"], [])
                    self.assertTrue(result["read_only"])
                    self.assertEqual(len(result["skill_keys"]), len(set(result["skill_keys"])))
                    self.assertFalse(report["installed"])
                    self.assertEqual({entry["source"] for entry in report["selected"]}, {"bundled"})

    def test_synthetic_registry_exercises_real_discovery_and_selection(self):
        from tools.simulate_repositories import adversarial_checks

        with tempfile.TemporaryDirectory(prefix="auto-skills-registry-test-") as directory:
            results = adversarial_checks(Path(directory))
        self.assertGreaterEqual(len(results), 7)
        for result in results:
            with self.subTest(check=result["name"]):
                self.assertTrue(result["passed"], json.dumps(result, ensure_ascii=True))
                self.assertTrue(result["read_only"])
                self.assertGreater(result["registry_snapshots"], 0)

    def test_tool_inventory_is_actual_installer_offline_output(self):
        from tools.simulate_repositories import tool_inventory

        with (
            tempfile.TemporaryDirectory(prefix="auto-skills-tool-inventory-") as directory,
            patch("codex_bootstrap.token_tools.shutil.which", return_value=None),
        ):
            tools = tool_inventory(Path(directory))
        self.assertEqual(
            {tool["name"] for tool in tools}, {"rtk", "repomix", "repo-map", "token-run"}
        )
        unavailable = {tool["name"] for tool in tools if tool["status"] == "unavailable"}
        self.assertEqual(unavailable, {"rtk"})
        self.assertEqual(
            {tool["name"] for tool in tools if tool["status"] == "deferred"}, {"repomix"}
        )

    def test_database_driver_versions_are_not_reported_as_verified_engine_versions(self):
        from tools.repo_scenarios import SCENARIOS
        from tools.simulate_repositories import assess_scenario

        with tempfile.TemporaryDirectory(prefix="auto-skills-db-roles-") as directory:
            for spec in SCENARIOS:
                expected = {
                    "go-gin-service",
                    "rust-web-service",
                    "driver-only-node",
                    "driver-only-python",
                    "driver-only-sqlite",
                }
                if spec.slug in expected:
                    with self.subTest(repository=spec.slug):
                        result, _ = assess_scenario(spec, Path(directory) / spec.slug)
                        self.assertEqual(result["version_role_gaps"], [])
                        self.assertEqual(result["verdict"], "Cohérent")

    def test_documentation_has_reduced_baseline_and_tools(self):
        from tools.repo_scenarios import SCENARIOS
        from tools.simulate_repositories import assess_scenario

        spec = next(s for s in SCENARIOS if s.slug == "documentation-only")
        with tempfile.TemporaryDirectory() as directory:
            result, report = assess_scenario(spec, Path(directory) / spec.slug)
        self.assertLess(len(report["selected"]), 10)
        self.assertFalse(
            {"build", "unit-testing", "performance"} & {e["slot"] for e in report["selected"]}
        )
        self.assertEqual({e["name"] for e in result["tool_plan"]}, {"token-run", "repo-map"})
        self.assertTrue(all(not scenario.known_gaps for scenario in SCENARIOS))

    def test_live_errors_count_only_new_errors_for_each_scenario(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from tools import simulate_repositories as matrix
        from tools.repo_scenarios import SCENARIOS

        original_propose = matrix.propose
        github = SimpleNamespace(
            errors=[{"reason": "earlier failure"}, {"reason": "older failure"}]
        )

        def propose_with_shared_history(root, *, offline, github):
            github.errors.append({"reason": "current failure"})
            report = original_propose(root, offline=True)
            report["discovery"]["errors"] = list(github.errors)
            return report

        spec = next(s for s in SCENARIOS if s.slug == "documentation-only")
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(matrix, "propose", side_effect=propose_with_shared_history):
                result, report = matrix.assess_scenario(
                    spec, Path(directory) / spec.slug, live=True, github=github
                )
        self.assertEqual(result["discovery_errors"], 1)
        self.assertEqual(
            report["matrix_discovery_diagnostics"]["errors"], [{"reason": "current failure"}]
        )
        self.assertEqual(len(github.errors), 3)

    def test_internal_and_external_are_separate_and_synthetic_is_not_external(self):
        from tools.simulate_repositories import classified_skills

        entries = [
            {"name": "built", "slot": "documentation", "source": "bundled"},
            {
                "name": "remote",
                "slot": "framework-react",
                "source": "github",
                "repository": "real/skills",
                "commit": "a" * 40,
                "url": "https://github.com/real/skills/blob/" + "a" * 40 + "/SKILL.md",
                "reason": "matched technology; compatible",
            },
        ]
        internal, external = classified_skills(entries)
        self.assertEqual([e["name"] for e in internal], ["built"])
        self.assertEqual([e["name"] for e in external], ["remote"])
        self.assertTrue(external[0]["pinned"])
        self.assertEqual(external[0]["quality_scope"], "heuristic")
        entries[1]["repository"] = "simulation/skills"
        with self.assertRaises(ValueError):
            classified_skills(entries)

    def test_new_ambiguity_or_driver_version_fails_regression_gate(self):
        from tools.simulate_repositories import regression_failures

        clean = {
            "repository": "fixture",
            "read_only": True,
            "unexpected_slots": [],
            "unexpected_missing_slots": [],
            "ambiguous_versions": [],
            "version_role_gaps": [],
            "scope_gaps": [],
            "duplicate_skill_keys": [],
        }
        self.assertEqual(regression_failures([clean], []), [])
        for key in (
            "ambiguous_versions",
            "version_role_gaps",
            "scope_gaps",
            "duplicate_skill_keys",
        ):
            with self.subTest(key=key):
                self.assertEqual(
                    regression_failures([{**clean, key: ["regression"]}], []), ["fixture"]
                )


if __name__ == "__main__":
    unittest.main()
