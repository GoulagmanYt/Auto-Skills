import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from suite_support import IsolatedTestCase

from codex_bootstrap.bootstrap import bootstrap


class TaskDecisionTests(IsolatedTestCase):
    def test_french_security_prompt_selects_security_guidance(self):
        result = self.decision("Vérifie la sécurité du projet.")
        self.assertIn("security", [entry["slot"] for entry in result["selected"]])

    def test_cached_metadata_cannot_claim_consultation_or_model_requests(self):
        first = self.decision("Check Rust", session_id="metadata")
        state = next((self.directory / "cache/task-state-v1").rglob("*.json"))
        first["states"]["consulted"] = "observed"
        first["metrics"]["model_requests"] = 999
        state.write_text(json.dumps(first))
        result = self.decision("Check Rust", session_id="metadata")
        self.assertEqual(result["states"]["consulted"], "unobserved")
        self.assertEqual(result["metrics"]["model_requests"], 0)

    def test_invalid_cached_decisions_are_recomputed(self):
        import copy
        import hashlib

        first = self.decision("Check Rust", session_id="corrupt")
        state = next(
            (self.directory / "cache/task-state-v1").rglob(
                hashlib.sha256(b"corrupt").hexdigest() + ".json"
            )
        )
        invalid = [
            [],
            None,
            "wrong",
            {},
            {**first, "metrics": []},
            {**first, "scopes": ["frontend"]},
            {**first, "repository": {}},
        ]
        for value in invalid:
            with self.subTest(value=type(value).__name__):
                state.write_text(json.dumps(copy.deepcopy(value)), encoding="utf-8")
                result = self.decision("Check Rust", session_id="corrupt")
                self.assertFalse(result["cache_hit"])
                self.assertEqual(result["selected"], first["selected"])

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.root = self.directory / "repo"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "frontend").mkdir()
        (self.root / "frontend/package.json").write_text('{"dependencies":{"react":"^18.3"}}')
        (self.root / "backend").mkdir()
        (self.root / "backend/Cargo.toml").write_text(
            '[package]\nname="backend"\nversion="0.1.0"\n'
        )
        self.env = patch.dict(os.environ, {"CODEX_BOOTSTRAP_CACHE": str(self.directory / "cache")})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.lock = bootstrap(self.root, offline=True)

    def decision(self, prompt, **kwargs):
        from codex_bootstrap.task import prepare_task

        return prepare_task(self.root, prompt, offline=True, **kwargs)

    def test_rust_task_at_monorepo_root_excludes_frontend_specialties(self):
        decision = self.decision("Corrige le décodeur Rust dans backend/src/lib.rs")
        self.assertEqual(decision["scopes"], ["backend"])
        self.assertIn("language-rust", [s["slot"] for s in decision["selected"]])
        self.assertFalse(any("react" in s["slot"] for s in decision["selected"]))
        self.assertTrue(decision["excluded"])
        self.assertLessEqual(len(decision["selected"]), 20)

    def test_preserving_a_sibling_is_not_a_request_for_its_specialties(self):
        result = self.decision("Fix frontend/src/label.mjs. Preserve all backend files.")
        self.assertEqual(result["scopes"], ["frontend"])
        self.assertFalse(any("rust" in s["slot"] for s in result["selected"]))

    def test_new_task_replaces_previous_session_selection_without_installation(self):
        before = (self.root / ".codex/skills-lock.json").read_bytes()
        first = self.decision("Fix backend/src/lib.rs", session_id="same")
        second = self.decision("Fix frontend/src/App.tsx", session_id="same")
        self.assertNotEqual(first["scopes"], second["scopes"])
        self.assertFalse(any("rust" in s["slot"] for s in second["selected"]))
        self.assertEqual(before, (self.root / ".codex/skills-lock.json").read_bytes())
        self.assertEqual(second["states"]["consulted"], "unobserved")

    def test_identical_return_avoids_model_network_and_state_rewrite(self):
        first = self.decision("Check Rust ownership", session_id="repeat")
        with patch("codex_bootstrap.proposal.discover", side_effect=AssertionError("network")):
            second = self.decision("Check Rust ownership", session_id="repeat")
        self.assertEqual(first["decision_id"], second["decision_id"])
        self.assertTrue(second["cache_hit"])
        self.assertEqual(second["metrics"]["model_requests"], 0)

    def test_agent_proposal_cannot_escape_workspaces_or_inject_sources(self):
        invalid = [
            {"scopes": ["../outside"], "capabilities": ["language-rust"]},
            {"scopes": ["backend"], "capabilities": ["framework-react"]},
            {"scopes": ["backend"], "capabilities": [], "repositories": ["evil/repo"]},
            {"scopes": ["backend"], "capabilities": [], "files": ["frontend/src/App.tsx"]},
            {"scopes": ["backend"], "capabilities": [], "files": ["../secret"]},
            {"scopes": ["backend"], "capabilities": [], "files": [], "reasons": "bad"},
        ]
        for proposal in invalid:
            with self.subTest(proposal=proposal), self.assertRaises(ValueError):
                self.decision("work", proposal={"schema_version": 1, "reasons": {}, **proposal})

    def test_existing_agent_can_submit_justified_scoped_decision(self):
        decision = self.decision(
            "Fix bug",
            proposal={
                "schema_version": 1,
                "scopes": ["backend"],
                "files": ["backend/src/lib.rs"],
                "capabilities": ["language-rust", "unit-testing"],
                "reasons": {"language-rust": "Rust ownership in the decoder"},
            },
        )
        self.assertEqual(decision["method"], "validated-agent-proposal")
        self.assertEqual(decision["scopes"], ["backend"])

    def test_git_identity_changes_invalidate_task_cache(self):
        first = self.decision("Check Rust", session_id="branch")
        subprocess.run(
            ["git", "-C", str(self.root), "symbolic-ref", "HEAD", "refs/heads/other"], check=True
        )
        second = self.decision("Check Rust", session_id="branch")
        self.assertNotEqual(first["decision_id"], second["decision_id"])
        self.assertFalse(second["cache_hit"])

    def test_editing_root_level_task_target_invalidates_decision(self):
        target = self.root / "main.py"
        target.write_text("value = 1\n")
        first = self.decision("Fix main.py", session_id="root-file")
        target.write_text("value = 2\n")
        second = self.decision("Fix main.py", session_id="root-file")
        self.assertEqual(first["files"], ["main.py"])
        self.assertFalse(second["cache_hit"])
        self.assertNotEqual(first["decision_id"], second["decision_id"])

    def test_workspace_relative_task_target_is_hashed(self):
        path = self.root / "backend/src/lib.rs"
        path.parent.mkdir()
        path.write_text("fn main() {}")
        result = self.decision("Fix src/lib.rs", cwd=self.root / "backend")
        self.assertEqual(result["files"], ["backend/src/lib.rs"])

    def test_capability_request_does_not_publish_after_manifest_drift(self):
        from codex_bootstrap.proposal import selection_plan

        before = (self.root / ".codex/skills-lock.json").read_bytes()

        def acquire(*args, **kwargs):
            result = selection_plan(*args, **kwargs)
            (self.root / "frontend/package.json").write_text('{"dependencies":{"react":"^19"}}')
            return result

        proposal = {
            "schema_version": 1,
            "scopes": ["frontend"],
            "capabilities": ["e2e-testing"],
            "files": [],
            "reasons": {"e2e-testing": "Validate browser behavior"},
        }
        with (
            patch("codex_bootstrap.proposal.selection_plan", side_effect=acquire),
            self.assertRaisesRegex(RuntimeError, "manifests changed"),
        ):
            self.decision("browser checks", proposal=proposal)
        self.assertEqual(before, (self.root / ".codex/skills-lock.json").read_bytes())

    def test_capability_request_reuses_preexisting_repository_guide(self):
        from test_automatic_inventory import guide

        # The skill was present before first preparation, although no initial
        # profile role required it; it remains unowned user content.
        other = self.directory / "local-request"
        other.mkdir()
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        (other / "package.json").write_text('{"dependencies":{"react":"^18"}}')
        local = other / ".agents/skills/browser-guide/SKILL.md"
        local.parent.mkdir(parents=True)
        local.write_text(guide("browser-guide", "e2e-testing").replace("Rust", "browser"))
        bootstrap(other, offline=True)
        from codex_bootstrap.task import prepare_task

        result = prepare_task(
            other,
            "browser checks",
            offline=True,
            proposal={
                "schema_version": 1,
                "scopes": ["."],
                "capabilities": ["e2e-testing"],
                "files": [],
                "reasons": {"e2e-testing": "Verify browser behavior"},
            },
        )
        chosen = next(s for s in result["selected"] if s["slot"] == "e2e-testing")
        self.assertEqual(chosen["source"], "local")
        self.assertEqual(chosen["name"], "browser-guide")

    def test_multiscope_capability_request_shares_one_discovery_budget(self):
        from codex_bootstrap.proposal import selection_plan
        from codex_bootstrap.task import prepare_task

        with (
            patch("codex_bootstrap.proposal.selection_plan", wraps=selection_plan) as choose,
            patch("codex_bootstrap.proposal.discover", return_value=([], {})),
        ):
            prepare_task(
                self.root,
                "browser checks",
                proposal={
                    "schema_version": 1,
                    "scopes": ["frontend", "backend"],
                    "capabilities": ["e2e-testing"],
                    "files": [],
                    "reasons": {"e2e-testing": "Cross-workspace browser validation"},
                },
            )
        clients = [call.kwargs.get("github") for call in choose.call_args_list]
        self.assertEqual(len(clients), 2)
        self.assertIsNotNone(clients[0])
        self.assertIs(clients[0], clients[1])

    def test_moved_checkout_cannot_reuse_old_task_identity(self):
        from codex_bootstrap.task import prepare_task

        first = self.decision("Check Rust", session_id="move")
        moved = (self.directory / "moved-repository").resolve()
        self.assertTrue(self.root.resolve().is_relative_to(self.directory.resolve()))
        self.assertTrue(moved.is_relative_to(self.directory.resolve()))
        self.root.rename(moved)
        second = prepare_task(moved, "Check Rust", session_id="move", offline=True)
        self.assertNotEqual(first["decision_id"], second["decision_id"])
        self.assertFalse(second["cache_hit"])

    def test_linked_worktree_has_separate_task_state(self):
        from codex_bootstrap.task import prepare_task

        subprocess.run(
            ["git", "-C", str(self.root), "add", "backend/Cargo.toml", "frontend/package.json"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "-c",
                "user.name=fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "commit",
                "-m",
                "fixture",
            ],
            check=True,
            capture_output=True,
        )
        other = self.directory / "linked-worktree"
        subprocess.run(
            [
                "git",
                "-C",
                str(self.root),
                "worktree",
                "add",
                "-q",
                "-b",
                "task-fixture",
                str(other),
            ],
            check=True,
            capture_output=True,
        )
        first = self.decision("Check Rust", session_id="shared-session")
        second = prepare_task(other, "Check Rust", session_id="shared-session", offline=True)
        self.assertNotEqual(
            first["repository"]["git_directory"], second["repository"]["git_directory"]
        )
        self.assertNotEqual(first["decision_id"], second["decision_id"])
        self.assertFalse(second["cache_hit"])

    def test_optional_task_cache_failure_keeps_verified_guidance_available(self):
        with patch("codex_bootstrap.task.atomic_write", side_effect=PermissionError("cache busy")):
            result = self.decision("Fix Rust", session_id="unwritable")
        self.assertTrue(result["selected"])
        self.assertEqual(result["metrics"]["cache_errors"], 1)

    def test_unknown_repository_gets_common_guidance_and_explicit_uncertainty(self):
        other = self.directory / "unknown"
        other.mkdir()
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        (other / "source.unheardof").write_text("opaque")
        from codex_bootstrap.task import prepare_task

        decision = prepare_task(other, "Fix this project", offline=True)
        self.assertTrue(decision["selected"])
        self.assertTrue(decision["uncertainties"])
        self.assertEqual(decision["metrics"]["model_requests"], 0)

    def test_session_state_never_stores_prompt_or_private_origin(self):
        self.decision("Fix Rust PRIVATE_TASK_TOKEN", session_id="../../unsafe")
        content = "".join(
            p.read_text() for p in (self.directory / "cache/task-state-v1").rglob("*.json")
        )
        self.assertNotIn("PRIVATE_TASK_TOKEN", content)
        self.assertNotIn("../../unsafe", content)
        json.loads(next((self.directory / "cache/task-state-v1").rglob("*.json")).read_text())

    def test_agent_can_acquire_missing_portable_capability_through_manager(self):
        before = {
            p: (self.root / p).stat().st_mtime_ns
            for p in self.lock["files"]
            if "language-rust/" in p
        }
        decision = self.decision(
            "Exercise browser flow",
            proposal={
                "schema_version": 1,
                "scopes": ["frontend"],
                "files": [],
                "capabilities": ["e2e-testing"],
                "reasons": {"e2e-testing": "Need browser validation of this UI flow"},
            },
        )
        self.assertIn("e2e-testing", [s["slot"] for s in decision["selected"]])
        self.assertEqual(before, {p: (self.root / p).stat().st_mtime_ns for p in before})
        updated = bootstrap(self.root, offline=True)
        self.assertTrue(
            any(s["slot"] == "e2e-testing" and s["scope"] == "frontend" for s in updated["skills"])
        )
        self.assertFalse(
            any(s["slot"] == "e2e-testing" and s["scope"] == "backend" for s in updated["skills"])
        )


if __name__ == "__main__":
    unittest.main()
