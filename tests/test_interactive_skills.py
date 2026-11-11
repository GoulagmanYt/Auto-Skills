"""Verifier invariants: actual guide reads and bounded persistent RPC handling."""

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from suite_support import IsolatedTestCase

from tools.verify_interactive_skills import RpcClient, demonstrate, observed_reads


class InteractiveEvidenceTests(IsolatedTestCase):
    def test_read_evidence_excludes_mentions_failed_commands_and_wrong_guides(self):
        lock = {
            "skills": [
                {
                    "scope": "backend",
                    "slot": "language-rust",
                    "name": "fixture-rust",
                    "path": ".codex/managed/rust/SKILL.md",
                    "discovery_path": ".agents/skills/rust/SKILL.md",
                },
                {
                    "scope": "frontend",
                    "slot": "framework-react",
                    "name": "fixture-react",
                    "path": ".codex/managed/react/SKILL.md",
                    "discovery_path": ".agents/skills/react/SKILL.md",
                },
            ]
        }

        def event(command, output, code=0):
            return {
                "method": "item/completed",
                "params": {
                    "item": {
                        "type": "commandExecution",
                        "command": command,
                        "aggregatedOutput": output,
                        "exitCode": code,
                    }
                },
            }

        events = [
            event(
                "Get-Content .agents/skills/rust/SKILL.md",
                "---\nname: fixture-rust\n---\nDo useful work.",
            ),
            event("echo .agents/skills/react/SKILL.md", "---\nname: fixture-react\n---\n"),
            event("cat .agents/skills/react/SKILL.md", "name: fixture-react\n", 1),
            event("cat .agents/skills/react/SKILL.md", "missing"),
        ]
        self.assertEqual(observed_reads(events, lock), ["backend::language-rust"])

    def test_notifications_before_reply_survive_and_turns_share_process(self):
        # A real child process exercises stdio ordering without authentication
        # or inference. It deliberately completes each turn before its reply.
        source = """import json,sys
count=0
for line in sys.stdin:
    request=json.loads(line)
    if request.get('method') == 'turn/start':
        count+=1
        turn={'id':str(count),'status':'completed'}
        print(json.dumps({'method':'turn/completed','params':{'threadId':'same-thread','turn':turn}}),flush=True)
        print(json.dumps({'id':request['id'],'result':{'turn':turn}}),flush=True)
    elif 'id' in request:
        print(json.dumps({'id':request['id'],'result':{}}),flush=True)
"""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            script = root / "server.py"
            script.write_text(source)
            client = RpcClient(
                [sys.executable, "-u", script], cwd=root, env=dict(os.environ), evidence=root
            )
            try:
                pid = client.process.pid
                first, events, _ = client.turn("same-thread", "first", timeout=3)
                second, _, _ = client.turn("same-thread", "second", timeout=3)
                self.assertEqual((first["id"], second["id"]), ("1", "2"))
                self.assertEqual(client.process.pid, pid)
                self.assertIsNone(client.process.poll())
                self.assertEqual(events[0]["method"], "turn/completed")
            finally:
                client.close()
            evidence = [
                json.loads(line)
                for line in (root / "interactive-rpc.jsonl").read_text().splitlines()
            ]
            self.assertEqual(sum(row["direction"] == "sent" for row in evidence), 2)

    def test_rpc_wait_has_deadline_and_failure_is_not_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            client = RpcClient(
                [sys.executable, "-u", "-c", "import sys; sys.stdin.read()"],
                cwd=root,
                env=dict(os.environ),
                evidence=root,
            )
            try:
                started = time.monotonic()
                with self.assertRaises(TimeoutError):
                    client.turn("same-thread", "never-replied", timeout=0.05)
                self.assertLess(time.monotonic() - started, 2)
            finally:
                client.close()

    def test_submitted_timeout_is_retained_as_indeterminate_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "evidence"
            evidence.mkdir()
            client = MagicMock()
            client.request.side_effect = [
                {"userAgent": "fixture"},
                {"thread": {"id": "same-thread"}},
            ]
            client.turn.side_effect = TimeoutError("fixture deadline")
            with (
                patch("tools.verify_interactive_skills.RpcClient", return_value=client),
                patch("tools.verify_interactive_skills.bootstrap", return_value={"skills": []}),
                patch("tools.verify_interactive_skills.prepare_task", return_value={}),
                patch("tools.verify_interactive_skills.verify_lock", return_value={"skills": []}),
                patch("tools.verify_interactive_skills.launch_overrides", return_value=[]),
                patch("tools.verify_interactive_skills.hook_overrides", return_value=[]),
            ):
                report = demonstrate(
                    Path(sys.executable), root, evidence, model="fixture", timeout=1
                )
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["failure_type"], "TimeoutError")
            self.assertEqual(report["metrics"]["planned_turns"], 4)
            self.assertEqual(report["metrics"]["attempted_turns"], 1)
            self.assertEqual(report["metrics"]["completed_turns"], 0)
            self.assertEqual(report["turns"][0]["status"], "indeterminate")
            client.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
