import os
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path
from unittest.mock import patch

from suite_support import IsolatedTestCase


class RuntimeRegressions(IsolatedTestCase):
    def test_profile_preserves_model_effort_and_cli_selection(self):
        from codex_bootstrap.bootstrap import bootstrap
        from codex_bootstrap.config import launch_profile

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            lock = bootstrap(root, offline=True)
            home = Path(os.environ["CODEX_HOME"])
            home.mkdir(parents=True, exist_ok=True)
            (home / "config.toml").write_text(
                '[profiles.preferred]\nmodel="chosen-model"\nmodel_reasoning_effort="high"\n'
            )
            args = ["--profile", "preferred", "--model", "explicit-model", "exec", "prompt"]
            with launch_profile(root, lock, args) as launch:
                data = tomllib.loads((home / (launch[1] + ".config.toml")).read_text())
                self.assertEqual(data["model"], "chosen-model")
                self.assertEqual(data["model_reasoning_effort"], "high")
                self.assertEqual(launch[2:], args[2:])

    def test_upgrade_migrates_owned_defaults_and_runtime(self):
        from codex_bootstrap.bootstrap import bootstrap, verify_lock
        from codex_bootstrap.config import local_config
        from codex_bootstrap.fs import digest, json_text

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            lock = bootstrap(root, offline=True)
            legacy = (
                "# Generated defaults; the wrapper also supplies explicit launch overrides.\n"
                'model_reasoning_effort = "low"\n'
            )
            for relative in (".codex/config.toml", ".codex/bootstrap.config.toml"):
                (root / relative).write_bytes(legacy.encode())
                lock["files"][relative] = digest(root / relative)
            for tool in lock["tools"]:
                if tool["name"] in {"token-run", "repo-map"}:
                    tool["version"] = "1"
            guide = next(s for s in lock["skills"] if s["slot"] == "token-reasoning")
            for key in ("path", "discovery_path"):
                path = root / guide[key]
                content = path.read_text(encoding="utf-8").replace(
                    "Preserve the user's selected model and model_reasoning_effort.",
                    "The wrapper defaults model_reasoning_effort to low.",
                )
                path.write_text(content, encoding="utf-8")
                lock["files"][guide[key]] = digest(path)
            guide["sha256"] = digest(root / guide["path"])
            (root / ".codex/skills-lock.json").write_text(json_text(lock), encoding="utf-8")
            updated = bootstrap(root, offline=True)
            verify_lock(root)
            self.assertEqual((root / ".codex/config.toml").read_text(), local_config())
            for key in ("path", "discovery_path"):
                self.assertNotIn("The wrapper defaults", (root / guide[key]).read_text())
            self.assertTrue(
                all(
                    t["version"] == "2"
                    for t in updated["tools"]
                    if t["name"] in {"token-run", "repo-map"}
                )
            )

    def test_generated_config_does_not_override_user_effort(self):
        from codex_bootstrap.config import local_config

        self.assertNotIn("model_reasoning_effort", tomllib.loads(local_config()))

    def test_unicode_child_with_legacy_parent_encoding(self):
        from codex_bootstrap.token_tools import install_token_tools

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            install_token_tools(root / ".codex", offline=True, enabled=set())
            result = subprocess.run(
                [
                    sys.executable,
                    str(root / ".codex/bin/token-run.py"),
                    "--",
                    sys.executable,
                    "-c",
                    "print(chr(8209))",
                ],
                env={**os.environ, "PYTHONIOENCODING": "cp1252"},
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn(chr(8209).encode(), result.stdout)

    def test_nested_repo_map_launcher(self):
        from codex_bootstrap.token_tools import install_token_tools

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            install_token_tools(root / ".codex", offline=True, enabled=set())
            result = subprocess.run(
                [
                    sys.executable,
                    str(root / ".codex/bin/token-run.py"),
                    "--",
                    ".codex/bin/repo-map",
                    "--limit",
                    "5",
                ],
                cwd=root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_offline_reuses_available_rtk_without_download(self):
        from codex_bootstrap.token_tools import install_token_tools

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            binary = root / ("rtk.exe" if os.name == "nt" else "rtk")
            binary.write_bytes(b"local binary")
            with (
                patch("codex_bootstrap.token_tools.shutil.which", return_value=str(binary)),
                patch("codex_bootstrap.token_tools.command", return_value="rtk 1.1.0"),
            ):
                tools = install_token_tools(root / ".codex", offline=True, enabled={"rtk"})
            rtk = next(tool for tool in tools if tool["name"] == "rtk")
            self.assertEqual(rtk["status"], "installed")
            self.assertEqual((root / rtk["path"]).read_bytes(), binary.read_bytes())
