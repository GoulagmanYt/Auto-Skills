"""Evidence in the dashboard must not be confused with availability."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from suite_support import IsolatedTestCase


class DashboardTests(IsolatedTestCase):
    def test_cli_exposes_machine_readable_status(self):
        import io
        from contextlib import redirect_stdout

        from codex_bootstrap.cli import main

        output = io.StringIO()
        with (
            patch("codex_bootstrap.cli.git_root", return_value=self.root),
            patch("codex_bootstrap.cli.real_codex", return_value=["native-codex"]),
            patch(
                "codex_bootstrap.dashboard.native_integrations",
                return_value={"plugins": [], "mcp": []},
            ),
            redirect_stdout(output),
        ):
            self.assertEqual(main(["dashboard", "--repo", str(self.root), "--json"]), 0)
        self.assertEqual(json.loads(output.getvalue())["skills"][0]["slot"], "language-python")

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.guide = self.root / ".codex/skills/python/SKILL.md"
        self.guide.parent.mkdir(parents=True)
        self.guide.write_text("# Python guide\n")
        self.lock = {
            "skills": [
                {
                    "slot": "language-python",
                    "scope": ".",
                    "name": "Python",
                    "path": ".codex/skills/python/SKILL.md",
                }
            ]
        }
        (self.root / ".codex/skills-lock.json").write_text(json.dumps(self.lock))

    def observe(self, tool, arguments, response, call="call-1", session="one"):
        from codex_bootstrap.observations import record_tool_event

        event = {
            "hook_event_name": "PostToolUse",
            "tool_name": tool,
            "tool_input": arguments,
            "tool_response": response,
            "tool_use_id": call,
            "cwd": str(self.root),
        }
        with patch.dict(os.environ, {"CODEX_BOOTSTRAP_OBSERVATION_SESSION": session}):
            record_tool_event(self.root, event)

    def test_installed_skill_is_not_reported_as_consulted(self):
        from codex_bootstrap.dashboard import snapshot

        report = snapshot(self.root, session="one")
        self.assertEqual(report["skills"][0]["reads"], 0)
        self.assertEqual(report["skills"][0]["integrity"], "unverified")

    def test_native_string_output_of_a_wrapped_read_is_real_evidence(self):
        from codex_bootstrap.dashboard import snapshot

        content = "# Python guide\nAlways preserve ownership and validate input.\n"
        self.guide.write_text(content)
        self.observe(
            "Bash",
            {
                "command": f".codex/bin/token-run -- powershell -NoProfile -Command 'Get-Content \"{self.guide}\"'"
            },
            content,
        )
        self.assertEqual(snapshot(self.root, session="one")["skills"][0]["reads"], 1)

    def test_plain_string_without_guide_contents_is_not_success_evidence(self):
        from codex_bootstrap.dashboard import snapshot

        self.observe("Bash", {"command": f'Get-Content "{self.guide}"'}, "Access denied")
        self.assertEqual(snapshot(self.root, session="one")["skills"][0]["reads"], 0)

    def test_windows_call_operator_before_wrapper_is_supported(self):
        from codex_bootstrap.observations import literal_reads

        command = r"""& .\.codex\bin\token-run -- powershell -NoProfile -Command 'Get-Content "C:\project\.codex\skills\python\SKILL.md"' """
        self.assertEqual(literal_reads(command), [r"C:\project\.codex\skills\python\SKILL.md"])

    def test_unexecuted_python_read_is_not_consultation(self):
        from codex_bootstrap.dashboard import snapshot

        script = f"from pathlib import Path\ndef unused():\n    return Path({str(self.guide)!r}).read_text()"
        self.observe("Bash", {"command": f'python -c "{script}"'}, {"exit_code": 0, "stdout": ""})
        self.assertEqual(snapshot(self.root, session="one")["skills"][0]["reads"], 0)

    def test_successful_read_is_deduplicated_and_scoped_to_session(self):
        from codex_bootstrap.dashboard import snapshot

        for _ in range(2):
            self.observe("read_file", {"path": str(self.guide)}, {"content": "# Python guide"})
        self.assertEqual(snapshot(self.root, session="one")["skills"][0]["reads"], 1)
        self.assertEqual(snapshot(self.root, session="two")["skills"][0]["reads"], 0)

    def test_failed_read_and_merely_mentioning_path_are_not_consultation(self):
        from codex_bootstrap.dashboard import snapshot

        self.observe("read_file", {"path": str(self.guide)}, {"error": "denied"})
        self.observe("Bash", {"command": f"echo {self.guide}"}, {"exit_code": 0}, "call-2")
        self.assertEqual(snapshot(self.root, session="one")["skills"][0]["reads"], 0)

    def test_shell_read_and_plugin_errors_are_observed_without_saving_payloads(self):
        from codex_bootstrap.dashboard import snapshot
        from codex_bootstrap.observations import read_observations

        self.observe(
            "Bash",
            {"command": f'Get-Content "{self.guide}"'},
            {"exit_code": 0, "stdout": "secret-value"},
        )
        self.observe(
            "mcp__example__lookup",
            {"token": "secret-value"},
            {"isError": True, "content": [{"text": "secret-value"}]},
            "call-2",
        )
        with patch.dict(os.environ, {"CODEX_BOOTSTRAP_INTEGRATION_MODE": "coexist"}):
            report = snapshot(
                self.root,
                session="one",
                integrations={
                    "plugins": [
                        {
                            "id": "example@local",
                            "name": "example",
                            "enabled": True,
                            "servers": ["example"],
                        }
                    ],
                    "mcp": [{"name": "example", "enabled": True}],
                },
            )
        self.assertEqual(report["skills"][0]["reads"], 1)
        self.assertEqual(report["plugins"][0]["health"], "error")
        self.assertNotIn("secret-value", json.dumps(read_observations(self.root, "one")))

    def test_strict_policy_blocks_a_plugin_even_with_historical_success(self):
        from codex_bootstrap.dashboard import snapshot

        self.observe("mcp__example__lookup", {}, {"isError": False}, "call-3")
        integrations = {
            "plugins": [
                {"id": "example@local", "name": "example", "enabled": True, "servers": ["example"]}
            ],
            "mcp": [],
        }
        report = snapshot(self.root, session="one", integrations=integrations)
        self.assertFalse(report["plugins"][0]["available"])
        self.assertEqual(report["plugins"][0]["health"], "disabled")

    def test_unobserved_enabled_plugin_is_not_healthy(self):
        from codex_bootstrap.dashboard import snapshot

        integrations = {
            "plugins": [
                {"id": "example@local", "name": "example", "enabled": True, "servers": ["example"]}
            ],
            "mcp": [],
        }
        with patch.dict(os.environ, {"CODEX_BOOTSTRAP_INTEGRATION_MODE": "coexist"}):
            report = snapshot(self.root, session="one", integrations=integrations)
        self.assertEqual(report["plugins"][0]["health"], "unverified")

    def test_render_strips_terminal_controls_and_respects_small_terminal(self):
        from codex_bootstrap.dashboard import render, snapshot

        self.lock["skills"][0]["name"] = "unsafe\x1b[2J\nname"
        (self.root / ".codex/skills-lock.json").write_text(json.dumps(self.lock))
        text = render(snapshot(self.root), tab=0, width=30, height=8)
        self.assertNotIn("\x1b", text)
        self.assertLessEqual(len(text.splitlines()), 8)
        self.assertTrue(all(len(line) <= 30 for line in text.splitlines()))

    def test_lifecycle_adapter_records_tool_events_without_context_injection(self):
        from codex_bootstrap.hooks import handle_event
        from codex_bootstrap.observations import read_observations

        event = {
            "hook_event_name": "PostToolUse",
            "cwd": str(self.root),
            "tool_name": "mcp__example__lookup",
            "tool_input": {},
            "tool_response": {"isError": False},
            "tool_use_id": "from-hook",
        }
        with (
            patch("codex_bootstrap.hooks.git_root", return_value=self.root),
            patch.dict(os.environ, {"CODEX_BOOTSTRAP_OBSERVATION_SESSION": "one"}),
        ):
            self.assertEqual(handle_event(event), {})
        self.assertEqual(read_observations(self.root, "one")[0]["outcome"], "ok")
