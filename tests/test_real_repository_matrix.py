"""Network-free regression checks over attributed real upstream manifest extracts."""

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from suite_support import IsolatedTestCase

from tools.verify_real_repositories import (
    FIXTURES,
    assess_repositories,
    load_catalog,
    verify_snapshot,
)


class RealRepositoryMatrixTests(IsolatedTestCase):
    def test_genuine_pinned_manifests_classify_in_their_own_workspaces_offline(self):
        with (
            patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")),
            patch("subprocess.Popen", side_effect=AssertionError("project execution forbidden")),
        ):
            report = assess_repositories()
        self.assertGreaterEqual(len(report["repositories"]), 14)
        self.assertFalse(report["network_used_for_verification"])
        self.assertFalse(report["upstream_execution"])
        for result in report["repositories"]:
            with self.subTest(repository=result["repository"]):
                self.assertTrue(result["passed"], json.dumps(result["failures"]))
                self.assertTrue(result["read_only"])
                self.assertNotEqual(result["repository_kind"], "documentation")
        self.assertTrue(report["passed"])

    def copy_snapshot(self):
        temporary = tempfile.TemporaryDirectory(prefix="real-manifest-integrity-")
        self.addCleanup(temporary.cleanup)
        fixtures = Path(temporary.name)
        spec = copy.deepcopy(load_catalog()["repositories"][0])
        shutil.copytree(FIXTURES / spec["slug"], fixtures / spec["slug"])
        return spec, fixtures

    def test_copied_manifest_and_license_tampering_is_detected(self):
        for name in ("manifest.txt", "LICENSE.txt"):
            with self.subTest(file=name):
                spec, fixtures = self.copy_snapshot()
                self.assertEqual(verify_snapshot(spec, fixtures), [])
                path = fixtures / spec["slug"] / name
                path.write_bytes(path.read_bytes() + b"\nmodified\n")
                self.assertIn(f"SHA-256 mismatch: {name}", verify_snapshot(spec, fixtures))

    def test_mutable_commit_or_identity_mismatch_is_rejected(self):
        spec, fixtures = self.copy_snapshot()
        spec["commit"] = "main"
        self.assertTrue(
            any("immutable Git SHA" in error for error in verify_snapshot(spec, fixtures))
        )
        spec, fixtures = self.copy_snapshot()
        spec["commit"] = "a" * 40
        errors = verify_snapshot(spec, fixtures)
        self.assertIn("catalog/provenance mismatch: commit", errors)
        self.assertIn("manifest URL does not match pinned identity", errors)

    def test_missing_license_and_unsafe_original_path_are_rejected(self):
        spec, fixtures = self.copy_snapshot()
        (fixtures / spec["slug"] / "LICENSE.txt").unlink()
        self.assertTrue(verify_snapshot(spec, fixtures))
        spec, fixtures = self.copy_snapshot()
        spec["original_path"] = "../outside/package.json"
        self.assertTrue(
            any("unsafe relative path" in error for error in verify_snapshot(spec, fixtures))
        )

    def test_license_review_is_bound_to_the_exact_copied_notice(self):
        spec = next(spec for spec in load_catalog()["repositories"] if spec.get("license_review"))
        temporary = tempfile.TemporaryDirectory(prefix="real-license-review-")
        self.addCleanup(temporary.cleanup)
        fixtures = Path(temporary.name)
        shutil.copytree(FIXTURES / spec["slug"], fixtures / spec["slug"])
        provenance_path = fixtures / spec["slug"] / "provenance.json"
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        provenance["license_review"]["license_sha256"] = "0" * 64
        provenance_path.write_text(json.dumps(provenance), encoding="utf-8")
        self.assertIn(
            "license review does not match copied upstream notice", verify_snapshot(spec, fixtures)
        )

    def test_all_expectations_are_explicit_independent_catalog_data(self):
        catalog = load_catalog()
        slugs = [spec["slug"] for spec in catalog["repositories"]]
        self.assertEqual(len(slugs), len(set(slugs)))
        for spec in catalog["repositories"]:
            with self.subTest(repository=spec["repository"]):
                self.assertTrue(spec["expected_technologies"])
                self.assertTrue(spec["expected_slots"])
                self.assertTrue(spec["expected_language_slots"])
                self.assertTrue(set(spec["expected_slots"]) & set(spec["expected_language_slots"]))
                self.assertEqual(verify_snapshot(spec), [])


if __name__ == "__main__":
    unittest.main()
