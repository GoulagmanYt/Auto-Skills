import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/benchmark_tasks.py"


class TaskBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def benchmark(self):
        self.assertTrue(SCRIPT.is_file(), "Complete-task benchmark harness is missing")
        spec = importlib.util.spec_from_file_location("task_benchmark", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_dry_run_plans_explicit_model_three_repetitions_without_inference(self):
        result = subprocess.run(
            [
                "python",
                str(SCRIPT),
                "--dry-run",
                "--model",
                "fixture-model-2026-01-01",
                "--arms",
                "baseline,auto-skills",
                "--output",
                str(self.root / "out"),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads((self.root / "out/report.json").read_text())
        self.assertEqual(report["mode"], "dry-run")
        self.assertEqual(len(report["plan"]), 18)
        self.assertEqual(report["runs"], [])
        self.assertEqual(report["model"], "fixture-model-2026-01-01")
        self.assertEqual(report["repetitions"], 3)
        self.assertEqual(len({row["fixture_sha256"] for row in report["plan"]}), 3)

    def test_all_external_validators_reject_fixture_and_accept_reference_patch(self):
        bench = self.benchmark()
        for task in bench.load_tasks():
            with self.subTest(task=task["id"]):
                worktree = self.root / task["id"]
                shutil.copytree(bench.EXAMPLES / task["fixture"], worktree)
                before = bench.validate_task(task, worktree)
                if before["status"] == "unavailable":
                    self.skipTest(before["reason"])
                self.assertEqual(before["status"], "failed", before)
                shutil.copyfile(bench.EXAMPLES / task["reference_fix"], worktree / task["source"])
                self.assertEqual(bench.validate_task(task, worktree)["status"], "passed")

    def test_usage_uses_native_completion_events_and_preserves_missing_cache(self):
        bench = self.benchmark()
        events = "\n".join(
            json.dumps(item)
            for item in [
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 10, "cached_input_tokens": 4, "output_tokens": 2},
                },
                {
                    "type": "turn.completed",
                    "usage": {"input_tokens": 20, "cached_input_tokens": 9, "output_tokens": 3},
                },
            ]
        )
        self.assertEqual(bench.parse_usage(events)["input_tokens"], 30)
        self.assertEqual(bench.parse_usage(events)["cached_input_tokens"], 13)
        cumulative = (
            events
            + "\n"
            + json.dumps(
                {
                    "type": "thread.completed",
                    "usage": {"input_tokens": 30, "cached_input_tokens": 13, "output_tokens": 5},
                }
            )
        )
        self.assertEqual(bench.parse_usage(cumulative)["input_tokens"], 30)
        missing = bench.parse_usage(
            '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":2}}'
        )
        self.assertIsNone(missing["cached_input_tokens"])
        self.assertIsNone(bench.parse_usage('{"type":"error","message":"failure"}'))

    def test_summary_reports_failures_and_spread_without_fabricated_savings(self):
        bench = self.benchmark()
        rows = [
            {
                "task": "task",
                "arm": "baseline",
                "status": status,
                "elapsed_seconds": elapsed,
                "usage": {"input_tokens": tokens, "output_tokens": 2, "cached_input_tokens": 0},
            }
            for status, elapsed, tokens in [
                ("passed", 2, 100),
                ("failed", 4, 200),
                ("passed", 9, 900),
            ]
        ]
        rows.append(
            {
                "task": "task",
                "arm": "autoskills",
                "status": "unavailable",
                "elapsed_seconds": None,
                "usage": None,
            }
        )
        summary = bench.summarize(rows)
        self.assertEqual(summary[0]["successes"], 2)
        self.assertEqual(summary[0]["failures"], 1)
        self.assertEqual(summary[0]["elapsed_seconds"], {"n": 3, "median": 4, "min": 2, "max": 9})
        self.assertEqual(summary[0]["input_tokens"]["median"], 200)
        self.assertIsNone(summary[1]["input_tokens"]["median"])
        self.assertNotIn("savings", json.dumps(summary))

    def test_blocked_preflight_reports_unattempted_plan_without_native_calls(self):
        bench = self.benchmark()
        preflight = self.root / "preflight.json"
        preflight.write_text(
            json.dumps(
                {
                    "mode": "live",
                    "model": "fixture-model-2026-01-01",
                    "codex_version": "0.166.0",
                    "runs": [
                        {
                            "task": "midi-zero-velocity",
                            "arm": "baseline",
                            "status": "failed",
                            "diagnostic_categories": ["agent_reported_sandbox_restriction"],
                            "returncode": 0,
                            "usage": {"input_tokens": 10, "output_tokens": 2},
                            "elapsed_seconds": 4,
                        }
                    ],
                }
            )
        )
        args = bench.parser().parse_args(
            [
                "--model",
                "fixture-model-2026-01-01",
                "--blocked-preflight",
                str(preflight),
                "--output",
                str(self.root / "blocked"),
            ]
        )
        with patch.object(
            bench.subprocess, "run", side_effect=AssertionError("must not launch native calls")
        ):
            report = bench.run_benchmark(args)
        self.assertEqual(report["mode"], "blocked")
        self.assertEqual(len(report["runs"]), 18)
        self.assertTrue(
            all(row["status"] == "unavailable" and row["usage"] is None for row in report["runs"])
        )
        self.assertEqual(report["preflight"]["evidence"][0]["usage"]["input_tokens"], 10)

    def test_three_arm_orchestration_uses_identical_fixtures_and_validates_real_patches(self):
        bench = self.benchmark()
        real_run = subprocess.run
        real_popen = subprocess.Popen
        captured = []
        task = next(task for task in bench.load_tasks() if task["id"] == "frontend-reset")

        def native_boundary(command, **kwargs):
            if command[0] == "fake-codex":
                if "--version" in command:
                    return SimpleNamespace(returncode=0, stdout="codex-cli 0.166.0\n", stderr="")
                captured.append(command)
                worktree = Path(command[command.index("-C") + 1]).parent
                shutil.copyfile(bench.EXAMPLES / task["reference_fix"], worktree / task["source"])
                events = '{"type":"turn.completed","usage":{"input_tokens":30,"cached_input_tokens":10,"output_tokens":5}}\n'
                return SimpleNamespace(returncode=0, stdout=events, stderr="")
            if command[0] in {"npx", "npx.cmd"}:
                skill = Path(kwargs["cwd"]) / ".agents/skills/vercel-react-best-practices/SKILL.md"
                skill.parent.mkdir(parents=True, exist_ok=True)
                skill.write_text(
                    "---\nname: vercel-react-best-practices\ndescription: React guidance\n---\nKeep state transitions deterministic."
                )
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if command[0] == "git" and "fetch" in command:
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if command[0] == "git" and "checkout" in command:
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if (
                command[0] == "git"
                and "rev-parse" in command
                and Path(kwargs.get("cwd") or ".").name == "competitor-source"
            ):
                pin = bench.load_competitors()["vercel-skills"]["source_commit"]
                return SimpleNamespace(returncode=0, stdout=pin + "\n", stderr="")
            return real_run(command, **kwargs)

        def native_popen(command, **kwargs):
            if command[0] == "fake-codex":
                result = native_boundary(command)
                return SimpleNamespace(
                    returncode=result.returncode,
                    communicate=lambda *args, **kwargs: (result.stdout, result.stderr),
                )
            return real_popen(command, **kwargs)

        args = bench.parser().parse_args(
            [
                "--model",
                "fixture-model-2026-01-01",
                "--arms",
                "baseline,auto-skills,vercel-skills",
                "--task",
                "frontend-reset",
                "--repetitions",
                "1",
                "--codex",
                "fake-codex",
                "--output",
                str(self.root / "out"),
            ]
        )
        with (
            patch.dict("os.environ", {"CODEX_HOME": str(self.root / "codex-home")}),
            patch.object(bench.subprocess, "run", side_effect=native_boundary),
            patch.object(bench.subprocess, "Popen", side_effect=native_popen),
        ):
            report = bench.run_benchmark(args)
        self.assertEqual([row["status"] for row in report["runs"]], ["passed"] * 3)
        self.assertEqual(len({row["fixture_sha256"] for row in report["runs"]}), 1)
        self.assertEqual(len({row["fixture_commit"] for row in report["runs"]}), 1)
        self.assertEqual(len(captured), 3)
        for command in captured:
            self.assertIn("--json", command)
            self.assertIn("--ephemeral", command)
            self.assertEqual(command[command.index("--sandbox") + 1], "workspace-write")
            self.assertEqual(command[command.index("--model") + 1], "fixture-model-2026-01-01")
        self.assertFalse(list((self.root / "codex-home").glob("*.config.toml")))


if __name__ == "__main__":
    unittest.main()
