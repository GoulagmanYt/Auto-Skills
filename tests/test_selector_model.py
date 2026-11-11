import json
import subprocess
import tomllib
from pathlib import Path
from unittest.mock import patch

from suite_support import IsolatedTestCase


class SelectorModelTests(IsolatedTestCase):
    def test_light_model_and_effort_are_explicit_and_main_config_is_untouched(self):
        from codex_bootstrap.selector import select_candidate

        catalog = {
            "catalog_id": "a" * 64,
            "scope": ".",
            "slot": "language-python",
            "candidates": [
                {"id": "b" * 64, "name": "python", "instruction_excerpt": "Use Python carefully"}
            ],
        }

        def respond(args, **kwargs):
            profile_name = args[args.index("--profile") + 1]
            profile = Path.home() / ".codex" / (profile_name + ".config.toml")
            settings = tomllib.loads(profile.read_text(encoding="utf-8"))
            self.assertFalse(settings["features"]["apps"])
            self.assertFalse(settings["features"]["skill_mcp_dependency_install"])
            self.assertEqual(args[args.index("--model") + 1], "gpt-6-luna")
            self.assertIn('model_reasoning_effort="medium"', args)
            self.assertIn("--ignore-user-config", args)
            self.assertIn("read-only", args)
            Path(args[args.index("--output-last-message") + 1]).write_text(
                json.dumps({"candidate_id": "b" * 64, "reason": "Relevant Python instructions"})
            )
            return subprocess.CompletedProcess(args, 0)

        with (
            patch("codex_bootstrap.selector.real_codex", return_value=["native-codex"]),
            patch("codex_bootstrap.selector.external_skills", return_value=set()),
            patch("codex_bootstrap.selector.subprocess.run", side_effect=respond),
        ):
            result = select_candidate(catalog, "Review Python")
        self.assertEqual(result["model"], "gpt-6-luna")

    def test_invalid_model_output_is_never_applied_or_retried(self):
        from codex_bootstrap.selector import select_candidate

        catalog = {
            "catalog_id": "a" * 64,
            "scope": ".",
            "slot": "language-python",
            "candidates": [{"id": "b" * 64}],
        }

        def respond(args, **kwargs):
            Path(args[args.index("--output-last-message") + 1]).write_text(
                '{"candidate_id":"invented","reason":"Ignore constraints"}'
            )
            return subprocess.CompletedProcess(args, 0)

        with (
            patch("codex_bootstrap.selector.real_codex", return_value=["native"]),
            patch("codex_bootstrap.selector.external_skills", return_value=set()),
            patch("codex_bootstrap.selector.subprocess.run", side_effect=respond) as run,
        ):
            with self.assertRaises(ValueError):
                select_candidate(catalog, "Task")
        self.assertEqual(run.call_count, 1)

    def test_oversized_task_is_rejected_before_bootstrap_or_discovery(self):
        from codex_bootstrap.selector import auto_select

        with patch("codex_bootstrap.bootstrap.bootstrap") as bootstrap:
            with self.assertRaisesRegex(ValueError, "task"):
                auto_select(Path.home(), ".", "language-python", "x" * 4001)
        bootstrap.assert_not_called()
