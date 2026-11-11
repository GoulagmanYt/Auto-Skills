import os
import socket
import unittest
from pathlib import Path

from suite_support import IsolatedTestCase


class IsolationTests(IsolatedTestCase):
    def test_user_cache_and_admin_roots_are_isolated_before_setup(self):
        from codex_bootstrap.config import skill_roots

        home = Path.home()
        self.assertEqual(Path(os.environ["CODEX_HOME"]), home / ".codex")
        self.assertEqual(Path(os.environ["CODEX_BOOTSTRAP_CACHE"]), home / "cache")
        self.assertNotIn(Path("/etc/codex/skills"), skill_roots(home))
        with self.assertRaisesRegex(AssertionError, "network forbidden"):
            with socket.socket() as connection:
                connection.connect(("127.0.0.1", 9))

    def test_each_test_receives_a_fresh_home_even_without_super_setup(self):
        observed = []

        class Probe(IsolatedTestCase):
            def setUp(self):
                observed.append(Path.home())

            def runTest(self):
                self.assertFalse((Path.home() / "sentinel").exists())
                (Path.home() / "sentinel").touch()

        for _ in range(2):
            result = unittest.TestResult()
            Probe().run(result)
            self.assertTrue(result.wasSuccessful(), result.errors + result.failures)
        self.assertNotEqual(observed[0], observed[1])
