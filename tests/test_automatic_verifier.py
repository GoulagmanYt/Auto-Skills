import io
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

from suite_support import IsolatedTestCase

from tools import verify_automatic_skills as verifier


class ConcurrentVerifierTests(IsolatedTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()

    def run_pair(self, script, **kwargs):
        helper = getattr(verifier, "run_concurrently", None)
        self.assertTrue(callable(helper), "concurrent runs must retain diagnostic output")
        return helper(
            [sys.executable, "-I", "-c", script],
            root=self.root,
            env=dict(os.environ),
            evidence=self.evidence,
            **kwargs,
        )

    def test_failure_reports_exit_codes_and_sanitized_bounded_logs(self):
        secret = "ghp_" + "s" * 24
        stderr = io.StringIO()
        script = f"import sys;print('x'*20000);print({secret!r},file=sys.stderr);sys.exit(7)"
        with redirect_stderr(stderr):
            self.assertEqual(self.run_pair(script), [7, 7])
        logs = list(self.evidence.glob("concurrent-bootstrap-*.log"))
        self.assertEqual(len(logs), 2)
        self.assertNotIn(secret, stderr.getvalue())
        self.assertIn("exited 7", stderr.getvalue())
        for path in logs:
            text = path.read_text()
            self.assertLessEqual(len(text), 4000)
            self.assertNotIn(secret, text)
            self.assertIn("<REDACTED>", text)

    def test_both_children_start_before_either_is_waited_on(self):
        script = (
            "import os,time;from pathlib import Path;"
            "Path(str(os.getpid())+'.ready').touch();deadline=time.monotonic()+5\n"
            "while len(list(Path('.').glob('*.ready')))<2:\n"
            " if time.monotonic()>deadline: raise SystemExit(9)\n"
            " time.sleep(0.02)\n"
        )
        self.assertEqual(self.run_pair(script), [0, 0])

    def test_timeout_reaps_both_children(self):
        children = []
        original = subprocess.Popen

        def start(*args, **kwargs):
            child = original(*args, **kwargs)
            children.append(child)
            return child

        with (
            patch.object(verifier.subprocess, "Popen", side_effect=start),
            redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.run_pair("import time;time.sleep(30)", timeout=0.5)
        self.assertEqual(len(children), 2)
        self.assertTrue(all(child.poll() is not None for child in children))
