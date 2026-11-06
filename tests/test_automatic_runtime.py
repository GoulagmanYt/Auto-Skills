import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from codex_bootstrap.bootstrap import bootstrap
from codex_bootstrap.config import launch_profile


class AutomaticRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = self.directory / "repo"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        for name, filename, content in (
            ("backend", "Cargo.toml", '[package]\nname="backend"\nversion="0.1.0"'),
            ("frontend", "package.json", '{"dependencies":{"react":"^18"}}'),
        ):
            path = self.root / name / filename
            path.parent.mkdir()
            path.write_text(content)
        environment = patch.dict(
            os.environ,
            {
                "CODEX_HOME": str(self.directory / "home/.codex"),
                "CODEX_BOOTSTRAP_CACHE": str(self.directory / "cache"),
                "CODEX_BOOTSTRAP_OFFLINE": "1",
            },
        )
        environment.start()
        self.addCleanup(environment.stop)

    def test_launch_native_selection_follows_task_without_changing_user_prompt(self):
        from codex_bootstrap.task import prepare_task

        decision = prepare_task(self.root, "Fix backend/src/lib.rs", offline=True)
        lock = bootstrap(self.root, offline=True)
        args = ["exec", "Fix backend/src/lib.rs", "--json"]
        with launch_profile(self.root, lock, args, self.root, decision=decision) as launch:
            import tomllib

            profile = Path(os.environ["CODEX_HOME"]) / (launch[1] + ".config.toml")
            config = tomllib.loads(profile.read_text())
            enabled = [s["path"] for s in config["skills"]["config"] if s["enabled"]]
            self.assertTrue(any("language-rust" in p for p in enabled))
            self.assertFalse(any("react" in p for p in enabled))
            self.assertEqual(launch[-3:], args)
            self.assertIn("Auto-Skills task decision", config["developer_instructions"])

    def test_each_user_prompt_hook_replaces_task_guides(self):
        from codex_bootstrap.hooks import handle_event

        first = handle_event(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(self.root),
                "session_id": "test",
                "prompt": "Fix backend/src/lib.rs",
            }
        )
        second = handle_event(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(self.root),
                "session_id": "test",
                "prompt": "Fix frontend/src/App.tsx",
            }
        )
        self.assertIn("language-rust", first["hookSpecificOutput"]["additionalContext"])
        context = second["hookSpecificOutput"]["additionalContext"]
        self.assertIn("framework-react", context)
        self.assertNotIn("language-rust:", context)
        self.assertNotIn("PRIVATE", json.dumps(second))

    def test_resume_hook_restores_valid_last_session_selection(self):
        from codex_bootstrap.hooks import handle_event

        handle_event(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(self.root),
                "session_id": "same",
                "prompt": "Fix backend/src/lib.rs",
            }
        )
        result = handle_event(
            {
                "hook_event_name": "SessionStart",
                "cwd": str(self.root),
                "session_id": "same",
                "source": "resume",
            }
        )
        self.assertIn("language-rust:", result["hookSpecificOutput"]["additionalContext"])

    def test_hook_error_is_explicit_and_keeps_the_user_request(self):
        from codex_bootstrap.hooks import main

        bootstrap(self.root, offline=True)
        (self.root / ".codex/skills/token-reasoning/SKILL.md").write_text("corrupted")
        output = io.StringIO()
        with (
            patch(
                "sys.stdin",
                io.StringIO(
                    json.dumps(
                        {
                            "hook_event_name": "UserPromptSubmit",
                            "cwd": str(self.root),
                            "prompt": "PRIVATE",
                        }
                    )
                ),
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(main(), 0)
        result = json.loads(output.getvalue())
        self.assertNotEqual(result.get("continue"), False)
        self.assertIn("Auto-Skills", result["systemMessage"])
        self.assertNotIn("PRIVATE", output.getvalue())

    def test_cli_task_command_accepts_agent_decision(self):
        from codex_bootstrap.cli import main

        proposal = self.directory / "decision.json"
        proposal.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "scopes": ["backend"],
                    "files": [],
                    "capabilities": ["language-rust"],
                    "reasons": {"language-rust": "ownership"},
                }
            )
        )
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(
                [
                    "task",
                    "--repo",
                    str(self.root),
                    "--proposal",
                    str(proposal),
                    "--offline",
                    "--json",
                ]
            )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["method"], "validated-agent-proposal")

    def test_prompt_extractor_understands_resume_options_without_consuming_stdin(self):
        from codex_bootstrap.cli import requested_prompt

        for args, expected in (
            (["exec", "-m", "model-name", "Fix Rust", "--json"], "Fix Rust"),
            (["exec", "resume", "--last", "Fix React"], "Fix React"),
            (["resume", "12345678-1234-1234-1234-123456789abc", "Fix Rust"], "Fix Rust"),
            (["exec", "-"], ""),
            (["exec", "--output-schema", "schema.json", "Work"], "Work"),
        ):
            self.assertEqual(requested_prompt(args), expected)


if __name__ == "__main__":
    unittest.main()
