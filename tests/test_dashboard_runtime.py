"""Dashboard I/O, malformed metadata and process lifetime regressions."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from pathlib import Path, PurePosixPath
from unittest.mock import patch

from suite_support import IsolatedTestCase


class DashboardRuntimeTests(IsolatedTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()

    def seed(self):
        from codex_bootstrap.observations import record_tool_event

        event = {
            "hook_event_name": "PostToolUse",
            "cwd": str(self.root),
            "tool_name": "mcp__example__lookup",
            "tool_response": {"isError": False},
            "tool_use_id": "known-call",
        }
        with patch.dict(os.environ, {"CODEX_BOOTSTRAP_OBSERVATION_SESSION": "one"}):
            record_tool_event(self.root, event)

    def test_refresh_reuses_unchanged_evidence_and_notices_replaced_records(self):
        from codex_bootstrap.observations import observation_directory, read_observations

        self.seed()
        cache = {}
        initial = read_observations(self.root, "one", cache=cache)
        original_read = Path.read_text
        reads = []

        def counting_read(path, *args, **kwargs):
            reads.append(path)
            return original_read(path, *args, **kwargs)

        with patch.object(Path, "read_text", counting_read):
            self.assertEqual(read_observations(self.root, "one", cache=cache), initial)
        self.assertEqual(reads, [])
        path = next(observation_directory(self.root, "one").glob("*.json"))
        value = json.loads(path.read_text())
        value["outcome"] = "error"
        path.write_text(json.dumps(value))
        self.assertEqual(read_observations(self.root, "one", cache=cache)[0]["outcome"], "error")
        path.unlink()
        self.assertEqual(read_observations(self.root, "one", cache=cache), [])
        self.assertEqual(cache, {})

    def test_malformed_evidence_does_not_hide_valid_observations(self):
        from codex_bootstrap.observations import observation_directory, read_observations

        self.seed()
        folder = observation_directory(self.root, "one")
        (folder / ("f" * 64 + ".json")).write_text(
            json.dumps(
                {"version": 1, "time": "invalid", "reads": None, "server": [], "outcome": "ok"}
            )
        )
        self.assertEqual(len(read_observations(self.root, "one")), 1)

    def test_invalid_outcome_does_not_crash_evidence_reader(self):
        from codex_bootstrap.observations import observation_directory, read_observations

        self.seed()
        folder = observation_directory(self.root, "one")
        (folder / ("e" * 64 + ".json")).write_text(
            json.dumps({"version": 1, "time": 1, "reads": [], "server": "example", "outcome": []})
        )
        self.assertEqual(len(read_observations(self.root, "one")), 1)

    def test_deep_json_does_not_hide_neighboring_evidence(self):
        from codex_bootstrap.observations import observation_directory, read_observations

        self.seed()
        folder = observation_directory(self.root, "one")
        (folder / ("d" * 64 + ".json")).write_text("[" * 15000 + "]" * 15000)
        self.assertEqual(len(read_observations(self.root, "one")), 1)

    def test_deep_native_inventory_is_reported_as_unavailable(self):
        from codex_bootstrap.dashboard import native_integrations

        report = native_integrations([sys.executable, "-c", "print('['*15000+']'*15000)"])
        self.assertEqual(len(report["errors"]), 2)

    def test_bad_lock_produces_a_dashboard_error_instead_of_crashing(self):
        from codex_bootstrap.dashboard import snapshot

        (self.root / ".codex").mkdir()
        for contents in (
            "[]",
            "[" * 15000 + "]" * 15000,
            '{"skills": [], "files": []}',
            '{"skills":[{"path":[]}]}',
        ):
            (self.root / ".codex/skills-lock.json").write_text(contents)
            with self.subTest(contents_length=len(contents)), self.assertRaises(ValueError):
                snapshot(self.root)

    def test_invalid_json_in_one_plugin_does_not_hide_other_plugins(self):
        from codex_bootstrap.dashboard import native_integrations

        plugin = self.root / "plugin"
        plugin.mkdir()
        (plugin / ".mcp.json").write_text("{broken")
        payload = {
            "installed": [
                {"name": "broken", "enabled": True, "source": {"path": str(plugin)}},
                {"name": "working", "enabled": True},
            ]
        }
        script = f"import sys,json;print(json.dumps({payload!r} if sys.argv[1]=='plugin' else []))"
        report = native_integrations([sys.executable, "-c", script])
        self.assertEqual([p["name"] for p in report["plugins"]], ["broken", "working"])

    def test_bad_plugin_manifest_keeps_inventory_available(self):
        from codex_bootstrap.dashboard import native_integrations

        plugin = self.root / "plugin"
        plugin.mkdir()
        (plugin / ".mcp.json").write_text("[]")
        payload = {
            "installed": [
                {
                    "name": "example",
                    "pluginId": "example@local",
                    "enabled": True,
                    "source": {"path": str(plugin)},
                }
            ]
        }
        script = f"import sys,json; print(json.dumps({payload!r} if sys.argv[1]=='plugin' else []))"
        report = native_integrations([sys.executable, "-c", script])
        self.assertEqual(len(report["plugins"]), 1)
        self.assertEqual(report["plugins"][0]["servers"], [])
        self.assertTrue(report["errors"])

    def test_cancelling_inventory_reaps_its_running_process(self):
        from codex_bootstrap.dashboard import native_integrations

        cancel = threading.Event()
        processes = []
        original_popen = subprocess.Popen

        def tracking_popen(*args, **kwargs):
            process = original_popen(*args, **kwargs)
            processes.append(process)
            return process

        timer = threading.Timer(0.2, cancel.set)
        timer.start()
        try:
            start = time.monotonic()
            with patch("subprocess.Popen", tracking_popen):
                native_integrations(
                    [sys.executable, "-c", "import time;time.sleep(60)"], cancel=cancel
                )
            self.assertLess(time.monotonic() - start, 3)
            self.assertEqual(len(processes), 1)
            self.assertIsNotNone(processes[0].poll())
        finally:
            timer.cancel()
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=2)

    def test_windows_wrapper_paths_are_parsed_on_posix_hosts(self):
        from codex_bootstrap.observations import literal_reads

        with patch("codex_bootstrap.observations.Path", PurePosixPath):
            self.assertEqual(
                literal_reads(r'& .\.codex\bin\token-run -- cat "guide.md"'), ["guide.md"]
            )

    def test_wide_characters_do_not_wrap_the_dashboard(self):
        from codex_bootstrap.dashboard import render

        report = {"repository": "測" * 40, "mode": "strict", "skills": [], "plugins": [], "mcp": []}
        text = render(report, width=30, height=12)
        widths = [
            sum(
                0
                if unicodedata.combining(c)
                else 2
                if unicodedata.east_asian_width(c) in {"W", "F"}
                else 1
                for c in line
            )
            for line in text.splitlines()
        ]
        self.assertTrue(all(width <= 30 for width in widths))

    def test_emoji_presentation_and_keycaps_respect_display_width(self):
        from codex_bootstrap.dashboard import render

        for text, base in (("❤️", "❤"), ("1️⃣", "1"), ("1⃣", "1")):
            with self.subTest(sequence=text):
                report = {
                    "repository": text * 40,
                    "mode": "strict",
                    "skills": [],
                    "plugins": [],
                    "mcp": [],
                }
                line = render(report, width=30, height=12).splitlines()[2]
                self.assertLessEqual(line.count(base), 12)
