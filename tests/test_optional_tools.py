import os
from pathlib import Path
from unittest.mock import patch

from suite_support import IsolatedTestCase


class OptionalToolTests(IsolatedTestCase):
    def test_deferred_repomix_refresh_keeps_its_new_node_runtime(self):
        from codex_bootstrap.lifecycle import refresh_tools

        root = Path.home() / "repo"
        (root / ".codex").mkdir(parents=True)
        config = Path(os.environ["CODEX_HOME"]) / "auto-skills.toml"
        config.parent.mkdir(parents=True)
        config.write_text('[automatic]\noptional_tools=["repomix"]\n')
        old = {
            "tools": [
                {"name": "token-run", "status": "installed"},
                {"name": "repo-map", "status": "installed"},
                {"name": "repomix", "status": "deferred"},
            ],
            "files": {},
        }
        installed = [
            {"name": "token-run", "status": "installed"},
            {"name": "repo-map", "status": "installed"},
            {"name": "repomix", "status": "installed"},
            {"name": "node", "status": "installed", "path": ".codex/plugins/node/bin/node"},
        ]
        with patch("codex_bootstrap.token_tools.install_token_tools", return_value=installed):
            tools, *_ = refresh_tools(root, old, [{"name": t["name"]} for t in old["tools"]])
        self.assertIn("node", {t["name"] for t in tools})
        self.assertEqual(len(tools), 4)

    def test_offline_return_does_not_retry_deferred_tool(self):
        import subprocess

        from codex_bootstrap.bootstrap import bootstrap

        root = Path.home() / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / "package.json").write_text('{"dependencies":{"react":"^19"}}')
        bootstrap(root, offline=True)
        config = Path(os.environ["CODEX_HOME"]) / "auto-skills.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('[automatic]\noptional_tools=["repomix"]\n')
        lock_path = root / ".codex/skills-lock.json"
        before = lock_path.read_bytes()
        bootstrap(root, offline=True)
        self.assertEqual(lock_path.read_bytes(), before)

    def test_online_preparation_defers_repomix_without_global_opt_in(self):
        from codex_bootstrap.token_tools import install_token_tools

        with patch(
            "codex_bootstrap.token_tools.install_repomix",
            side_effect=AssertionError("unexpected npm installation"),
        ):
            tools = install_token_tools(Path.home() / "stage", enabled={"repomix"})
        repomix = next(t for t in tools if t["name"] == "repomix")
        self.assertEqual(repomix["status"], "deferred")

    def test_global_opt_in_installs_repomix(self):
        from codex_bootstrap.token_tools import install_token_tools

        config = Path(os.environ["CODEX_HOME"]) / "auto-skills.toml"
        config.parent.mkdir(parents=True)
        config.write_text('[automatic]\noptional_tools=["repomix"]\n')
        with patch(
            "codex_bootstrap.token_tools.install_repomix",
            return_value=[{"name": "repomix", "status": "installed"}],
        ) as install:
            tools = install_token_tools(Path.home() / "stage", enabled={"repomix"})
        install.assert_called_once()
        self.assertEqual(tools[-1]["status"], "installed")
