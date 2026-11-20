import json
import os
import tomllib
from pathlib import Path

from suite_support import IsolatedTestCase

from codex_bootstrap.config import launch_profile


class TrustedProjectsTests(IsolatedTestCase):
    def setUp(self):
        self.home = Path(os.environ["CODEX_HOME"])
        self.home.mkdir(exist_ok=True)
        self.base = self.home / "config.toml"
        self.root = self.home.parent / "repo"
        self.root.mkdir()
        self.key = r"\\?\C:\Work\Δ.Mixed"
        self.table = "[projects." + json.dumps(self.key, ensure_ascii=False) + "]\r\n"
        self.lock = {"skills": []}

    def launch(self, *args, long=False):
        # Exercise the transport decision without depending on the host OS.
        prompt = "x" * 35000 if long else "inspect"
        return launch_profile(self.root, self.lock, [*args, "exec", prompt])

    def approve(self, args, level="trusted"):
        self.assertEqual(args[0], "--profile")
        path = self.home / (args[1] + ".config.toml")
        with path.open("ab") as stream:
            stream.write((self.table + 'trust_level="' + level + '"\r\n').encode())
        return path

    def test_short_policy_keeps_native_trust_destination(self):
        for args in [(), ("--profile", "work")]:
            with self.subTest(args=args), self.launch(*args) as argv:
                self.assertIn("-c", argv)
                self.assertNotIn("auto-bootstrap-", " ".join(argv))
                self.assertEqual(argv[-2:], ["exec", "inspect"])
                if args:
                    self.assertIn("work", argv)

    def test_long_policy_exports_only_native_trust_to_durable_profile(self):
        original = b'# private configuration\r\nmodel = "user-model" # keep\r\n'
        for selected in ("", "work"):
            with self.subTest(selected=selected):
                target = self.home / (selected + ".config.toml") if selected else self.base
                target.write_bytes(original)
                with self.launch(*(["--profile", selected] if selected else []), long=True) as argv:
                    temporary = self.approve(argv)
                self.assertFalse(temporary.exists())
                self.assertTrue(target.read_bytes().startswith(original))
                data = tomllib.loads(target.read_text(encoding="utf8"))
                self.assertEqual(data, {"model": "user-model", "projects": {self.key: {"trust_level": "trusted"}}})

    def test_visited_folder_is_not_approved(self):
        with self.launch(long=True):
            pass
        self.assertFalse(self.base.exists())

    def test_concurrent_revocation_wins_and_other_user_edits_survive(self):
        with self.launch(long=True) as argv:
            self.approve(argv)
            edited = ("# changed externally\r\n" + self.table + 'trust_level="untrusted"\r\n').encode()
            self.base.write_bytes(edited)
        self.assertEqual(self.base.read_bytes(), edited)

    def test_private_mcp_values_are_never_passed_on_argv(self):
        self.base.write_text('[mcp_servers.service]\ncommand="test"\nenv={HEADER="private-canary"}\n')
        with self.launch() as argv:
            self.assertNotIn("private-canary", " ".join(argv))
