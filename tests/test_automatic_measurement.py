import copy
import tempfile
import unittest
from pathlib import Path

from tools.measure_automatic_skills import (
    FIXTURES,
    markdown,
    relevance,
    score_selection,
    verify_spec,
)


class MeasurementTests(unittest.TestCase):
    def test_scoring_keeps_wrong_scope_extras_and_missing_roles(self):
        decision = {
            "scopes": ["backend", "frontend"],
            "selected": [
                {"scope": ".", "slot": "unit-testing", "source": "bundled"},
                {"scope": "frontend", "slot": "framework-react", "source": "bundled"},
                {"scope": "backend", "slot": "static-analysis", "source": "bundled"},
            ],
        }
        result = score_selection(decision, "backend", ["language-rust"], ["language-rust"])
        self.assertEqual(result["scope_precision"], 0.5)
        self.assertEqual(result["scope_recall"], 1)
        self.assertEqual(result["specialty_precision"], 0)
        self.assertEqual(result["missed_capabilities"], ["language-rust"])
        self.assertEqual(
            result["irrelevant_specialties"],
            [
                {"scope": "frontend", "slot": "framework-react"},
                {"scope": "backend", "slot": "static-analysis"},
            ],
        )

    def test_absence_is_unknown_precision_and_failed_recall(self):
        result = score_selection({"scopes": [], "selected": []}, "backend", ["language-rust"], [])
        self.assertIsNone(result["scope_precision"])
        self.assertIsNone(result["specialty_precision"])
        self.assertEqual(result["role_recall"], 0)

    def test_pinned_public_extracts_are_complete_and_relevance_retains_every_row(self):
        report = relevance()
        self.assertEqual(report["summary"]["planned"], 5)
        self.assertEqual(report["summary"]["measured"], 5)
        for row in report["repositories"]:
            with self.subTest(repository=row["repository"]):
                self.assertFalse(row["integrity_errors"])
                self.assertEqual(row["network_download_attempts"], 0)
                self.assertEqual(row["model_requests"], 0)
                self.assertTrue(row["unchanged_task_cache_hit"])
                self.assertTrue(row["owned_artifacts_unchanged_on_return"])
                self.assertTrue(row["manifest_unchanged"])

    def test_snapshot_tampering_is_rejected(self):
        import json
        import shutil

        catalog = json.loads((FIXTURES / "catalog.json").read_text(encoding="utf-8"))
        spec = copy.deepcopy(catalog["repositories"][0])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            shutil.copytree(FIXTURES / spec["slug"], root / spec["slug"])
            (root / spec["slug"] / "manifest.txt").write_text("tampered", encoding="utf-8")
            self.assertIn("SHA-256 mismatch: manifest.txt", verify_spec(spec, root))

    def test_report_does_not_hide_failed_or_missing_usage_rows(self):
        report = {
            "relevance": {"repositories": []},
            "complete_tasks": {
                "model": "fixture-model",
                "runs": [
                    {"task": "a", "arm": "baseline", "status": "failed", "usage": None},
                    {"task": "a", "arm": "auto-skills", "status": "not_attempted", "usage": None},
                ],
            },
        }
        result = markdown(report)
        self.assertIn("| a | baseline | failed | unavailable | None | None | None | None |", result)
        self.assertIn("not_attempted", result)
        self.assertIn("fixture-model with existing Codex auth", result)
        self.assertIn("does not support savings claims", result)


if __name__ == "__main__":
    unittest.main()
