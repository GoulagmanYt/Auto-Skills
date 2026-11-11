import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from suite_support import IsolatedTestCase

from tools.verify_native_install import (
    assert_catalog,
    catalog,
    isolated_environment,
    main,
    run,
    sanitized,
    snapshot,
)


def prompt(entries):
    return [
        {"content": [{"text": "<skills_instructions>\n" + entries + "\n</skills_instructions>"}]}
    ]


class NativeInstallVerifierTests(IsolatedTestCase):
    def test_native_catalog_expands_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = prompt(
                f"- `r0` = `{root.as_posix()}/.agents/skills`\n"
                "- rust: Rust guide (file: r0/rust/SKILL.md)"
            )
            self.assertEqual(
                catalog(data, root), [(root / ".agents/skills/rust/SKILL.md").resolve()]
            )

    def test_native_missing_and_duplicate_catalogs_fail(self):
        entry = "- rust: Rust guide (file: .agents/skills/rust/SKILL.md)"
        for data in ({}, [], prompt("none"), prompt(entry + "\n" + entry)):
            with self.subTest(data_shape=type(data).__name__), self.assertRaises(ValueError):
                catalog(data, Path.cwd())

    def test_unexpected_native_catalog_path_fails_even_if_guide_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "unlocked/SKILL.md"
            path.parent.mkdir()
            path.write_text("guide", encoding="utf-8")
            data = prompt(f"- rust: Rust guide (file: {path.as_posix()})")
            with self.assertRaisesRegex(ValueError, "1 missing, 1 unexpected"):
                assert_catalog(
                    data, root, root, {"skills": []}, [{"discovery_path": "locked/SKILL.md"}]
                )

    def test_missing_native_executable_cannot_be_a_successful_skip(self):
        with (
            patch("tools.verify_native_install.shutil.which", return_value=None),
            redirect_stderr(io.StringIO()) as stderr,
        ):
            with self.assertRaises(SystemExit) as raised:
                main(["--codex", "unavailable-native-codex"])
        self.assertEqual(raised.exception.code, 1)
        self.assertIn("no skip", stderr.getvalue())

    def test_native_checks_receive_canonical_temporary_directory(self):
        canonical = Path.cwd() / "canonical-temporary-directory"
        with (
            patch("tools.verify_native_install.shutil.which", return_value="native-codex"),
            patch("tools.verify_native_install.tempfile.TemporaryDirectory") as temporary,
            patch("tools.verify_native_install.Path.resolve", return_value=canonical),
            patch("tools.verify_native_install.native_check", return_value={}) as verify,
            redirect_stdout(io.StringIO()),
        ):
            temporary.return_value.__enter__.return_value = "aliased-temporary-directory"
            main([])
        self.assertEqual(verify.call_args.args[2], canonical)

    def test_clean_home_environment_removes_auth_and_source_injection(self):
        with patch.dict(
            os.environ, {"OPENAI_API_KEY": "private", "GH_TOKEN": "private", "PYTHONPATH": "src"}
        ):
            env = isolated_environment(Path(tempfile.gettempdir()) / "native-home")
        for key in ("OPENAI_API_KEY", "GH_TOKEN", "PYTHONPATH"):
            self.assertNotIn(key, env)
        self.assertEqual(env["PYTHONNOUSERSITE"], "1")
        self.assertEqual(Path(env["CODEX_HOME"]).parent, Path(env["HOME"]))

    def test_subprocess_failure_and_timeout_are_not_success(self):
        result = subprocess.CompletedProcess(["codex"], 3, stdout="", stderr="native failed")
        with patch("tools.verify_native_install.subprocess.run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "exited 3: native failed"):
                run(["codex"], cwd=Path.cwd(), env={})
        with patch(
            "tools.verify_native_install.subprocess.run",
            side_effect=subprocess.TimeoutExpired("codex", 1),
        ):
            with self.assertRaisesRegex(RuntimeError, "timeout"):
                run(["codex"], cwd=Path.cwd(), env={}, timeout=1)

    def test_sanitized_error_does_not_expose_credentials_or_personal_paths(self):
        credential = "sk-" + "x" * 40
        personal = "C:" + "/" + "Users/" + "private-person/project"
        message = sanitized(credential + " " + personal)
        self.assertNotIn(credential, message)
        self.assertNotIn("private-person", message)
        self.assertNotIn(
            "private-password", sanitized("https://user:private-password@example.invalid")
        )

    def test_snapshot_detects_timestamp_changes_even_with_same_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "guide.md"
            path.write_text("same", encoding="utf-8")
            before = snapshot(root, ["guide.md"])
            os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 2_000_000_000))
            self.assertNotEqual(before, snapshot(root, ["guide.md"]))
            json.dumps(before)


if __name__ == "__main__":
    unittest.main()
