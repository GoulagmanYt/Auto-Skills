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
        self.addCleanup(self._check_no_profiles)
        self.base = self.home / "config.toml"
        self.root = self.home.parent / "repo"
        self.root.mkdir()
        self.key = r"\\?\C:\Work\Δ.Mixed"
        self.table = "[projects." + json.dumps(self.key, ensure_ascii=False) + "]\r\n"
        self.lock = {"skills": []}

    def _check_no_profiles(self):
        self.assertEqual(list(self.home.glob("auto-bootstrap-*.config.toml")), [])

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
                self.assertEqual(
                    data,
                    {"model": "user-model", "projects": {self.key: {"trust_level": "trusted"}}},
                )

    def test_visited_folder_is_not_approved(self):
        with self.launch(long=True):
            pass
        self.assertFalse(self.base.exists())

    def test_concurrent_revocation_wins_and_other_user_edits_survive(self):
        with self.launch(long=True) as argv:
            self.approve(argv)
            edited = (
                "# changed externally\r\n" + self.table + 'trust_level="untrusted"\r\n'
            ).encode()
            self.base.write_bytes(edited)
        self.assertEqual(self.base.read_bytes(), edited)

    def test_private_mcp_values_are_never_passed_on_argv(self):
        self.base.write_text(
            '[mcp_servers.service]\ncommand="test"\nenv={HEADER="private-canary"}\n'
        )
        with self.launch() as argv:
            self.assertNotIn("private-canary", " ".join(argv))

    def test_disjoint_concurrent_sessions_retain_both_decisions(self):
        from contextlib import ExitStack

        with ExitStack() as stack:
            first = stack.enter_context(self.launch(long=True))
            second = stack.enter_context(self.launch(long=True))
            self.approve(first)
            second_path = self.home / (second[1] + ".config.toml")
            with second_path.open("ab") as out:
                out.write(b'[projects."other.key"]\ntrust_level="untrusted"\n')
        self.assertEqual(
            tomllib.loads(self.base.read_text(encoding="utf8"))["projects"],
            {self.key: {"trust_level": "trusted"}, "other.key": {"trust_level": "untrusted"}},
        )

    def test_inherited_decisions_are_not_exported_on_visit(self):
        original = (self.table + 'trust_level="trusted"\r\n').encode()
        self.base.write_bytes(original)
        for args in [(), ("--profile", "work")]:
            with self.launch(*args, long=True):
                pass
        self.assertEqual(self.base.read_bytes(), original)
        self.assertFalse((self.home / "work.config.toml").exists())

    def test_inline_table_and_multiline_text_survive_leaf_update(self):
        from codex_bootstrap.trust import _apply

        before = b"""# Keep inline formatting\r\nnote = '''\r\n[projects.other]\r\n'''\r\nprojects = { 'a.b' = { extra = 2, trust_level = 'untrusted' } }\r\n"""
        self.base.write_bytes(before)
        _apply(self.home, self.base.name, {"a.b": ["untrusted", "trusted", None]})
        self.assertEqual(self.base.read_bytes(), before.replace(b"'untrusted'", b'"trusted"'))

    def test_interrupted_publication_keeps_delta_without_restoring_revoked_grant(self):
        from unittest.mock import patch

        from codex_bootstrap import trust

        publish = trust._publish

        def interrupted(*args):
            publish(*args)
            raise OSError("simulated interruption after native file replacement")

        with (
            patch.object(trust, "_publish", interrupted),
            self.assertRaisesRegex(RuntimeError, "manual review"),
        ):
            with self.launch(long=True) as args:
                self.approve(args)
        self.base.unlink()  # Native revocation restores the original absent state.
        with self.launch(long=True):
            pass
        self.assertFalse(self.base.exists())
        receipts = list((self.home / "auto-skills-trust").glob("*.json"))
        self.assertEqual(len(receipts), 1)
        self.assertEqual(
            json.loads(receipts[0].read_bytes())["changes"], {self.key: [None, "trusted", None]}
        )

    def test_late_parent_table_does_not_shadow_project_insertion(self):
        from codex_bootstrap.trust import _apply

        self.base.write_bytes(b"[projects.a]\r\nx=nan\r\n[projects]\r\nother={}\r\n")
        _apply(self.home, self.base.name, {"a": [None, "trusted", None]})
        self.assertEqual(
            self.base.read_bytes(),
            b'[projects.a]\r\n"trust_level" = "trusted"\r\nx=nan\r\n[projects]\r\nother={}\r\n',
        )

    def test_revoked_inherited_trust_is_not_reintroduced_in_named_profile(self):
        initial = (self.table + 'trust_level="trusted"\r\n').encode()
        self.base.write_bytes(initial)
        with self.launch("--profile", "work", long=True) as args:
            self.approve(args)
            self.base.write_bytes(b"# explicitly cleared\r\n")
        self.assertFalse((self.home / "work.config.toml").exists())

    def test_removing_only_dotted_trust_field_preserves_comments_and_table(self):
        from codex_bootstrap.trust import _apply

        self.base.write_bytes(b'projects."a.b".trust_level="trusted" # preserve\r\n')
        _apply(self.home, self.base.name, {"a.b": ["trusted", None, None]})
        self.assertEqual(self.base.read_bytes(), b'projects."a.b" = {} # preserve\r\n')
