import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_bootstrap.config import launch_overrides


class IntegrationPolicyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / ".codex").mkdir()
        self.lock = {
            "skills": [
                {
                    "scope": ".",
                    "slot": "architecture",
                    "path": ".codex/skills/architecture/SKILL.md",
                    "discovery_path": ".agents/skills/architecture/SKILL.md",
                }
            ]
        }

    def config(self, text=""):
        (self.root / ".codex/integrations.toml").write_text(text)
        with (
            patch.dict(os.environ, {"CODEX_BOOTSTRAP_INTEGRATION_MODE": ""}),
            patch("codex_bootstrap.config.external_skills", return_value={"/external/SKILL.md"}),
            patch(
                "codex_bootstrap.config.config_layers",
                return_value=[
                    {
                        "mcp_servers": {
                            "notes": {"command": "notes-server"},
                            "other": {"command": "other"},
                        },
                        "plugins": {
                            "notes@registry": {"enabled": True},
                            "other@registry": {"enabled": True},
                        },
                    }
                ],
            ),
        ):
            return tomllib.loads("\n".join(launch_overrides(self.root, self.lock)[1::2]))

    def test_coexist_preserves_user_integrations_and_only_filters_owned_skills(self):
        config = self.config('[integrations]\nmode="coexist"\n')
        self.assertNotIn("mcp_servers", config)
        self.assertNotIn("plugins", config)
        self.assertNotIn("bundled", config["skills"])
        self.assertNotIn("/external/SKILL.md", {e["path"] for e in config["skills"]["config"]})
        paths = {e["path"]: e["enabled"] for e in config["skills"]["config"]}
        self.assertFalse(paths[str((self.root / self.lock["skills"][0]["path"]).resolve())])
        self.assertIn("remain available", config["developer_instructions"])

    def test_strict_can_explicitly_keep_selected_mcp_and_plugin(self):
        config = self.config(
            '[integrations]\nkeep_mcp=["notes"]\nkeep_plugins=["notes@registry"]\n'
        )
        self.assertNotIn("notes", config["mcp_servers"])
        self.assertNotIn("notes@registry", config["plugins"])
        self.assertFalse(config["mcp_servers"]["other"]["enabled"])
        self.assertFalse(config["plugins"]["other@registry"]["enabled"])

    def test_invalid_mode_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "integration"):
            self.config('[integrations]\nmode="typo"\n')

    def test_preview_reports_active_exclusions_and_estimate_without_writes(self):
        import subprocess

        from codex_bootstrap.bootstrap import bootstrap
        from codex_bootstrap.context_preview import inspect_context

        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "package.json").write_text('{"dependencies":{"react":"^19"}}')
        (self.root / "backend").mkdir()
        (self.root / "backend/Cargo.toml").write_text('[package]\nname="backend"\nversion="0.1.0"')
        bootstrap(self.root, offline=True)
        before = {
            p.relative_to(self.root).as_posix(): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        report = inspect_context(self.root, cwd=self.root / "backend")
        self.assertEqual(report["workspace"], "backend")
        self.assertIn("language-rust", {s["slot"] for s in report["active"]})
        self.assertNotIn("framework-react", {s["slot"] for s in report["active"]})
        self.assertIn("framework-react", {s["slot"] for s in report["excluded"]})
        self.assertGreater(report["catalog_cost"]["estimated_tokens"], 0)
        self.assertTrue(all(s["reason"] for s in report["active"] + report["excluded"]))
        after = {
            p.relative_to(self.root).as_posix(): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        self.assertEqual(before, after)

    def test_coexist_preserves_explicit_external_and_selected_profile_skill_selectors(self):
        from codex_bootstrap.config import launch_profile

        home = self.root / "codex-home"
        home.mkdir()
        (home / "config.toml").write_text(
            'skills.config=[{path="/external/explicit/SKILL.md",enabled=false}]\n'
            "[profiles.work]\n"
            'skills.config=[{path="/external/work/SKILL.md",enabled=true}]\n'
        )
        (self.root / ".codex/integrations.toml").write_text('[integrations]\nmode="coexist"\n')
        with patch.dict(
            os.environ, {"CODEX_HOME": str(home), "CODEX_BOOTSTRAP_INTEGRATION_MODE": ""}
        ):
            args = launch_overrides(self.root, self.lock)
            config = tomllib.loads("\n".join(args[1::2]))
            selectors = {e["path"]: e["enabled"] for e in config["skills"]["config"]}
            self.assertIs(selectors.get("/external/explicit/SKILL.md"), False)
            with launch_profile(self.root, self.lock, ["--profile", "work"]) as argv:
                profile = tomllib.loads((home / (argv[1] + ".config.toml")).read_text())
                selectors = {e["path"]: e["enabled"] for e in profile["skills"]["config"]}
                self.assertTrue(selectors.get("/external/work/SKILL.md"))

    def test_coexist_selected_empty_selector_array_replaces_base_selectors(self):
        from codex_bootstrap.config import launch_profile

        home = self.root / "codex-home"
        home.mkdir()
        (home / "config.toml").write_text(
            'skills.config=[{path="/external/base-only/SKILL.md",enabled=false}]\n'
            "[profiles.work]\nskills.config=[]\n"
        )
        (self.root / ".codex/integrations.toml").write_text('[integrations]\nmode="coexist"\n')
        with patch.dict(
            os.environ, {"CODEX_HOME": str(home), "CODEX_BOOTSTRAP_INTEGRATION_MODE": ""}
        ):
            with launch_profile(self.root, self.lock, ["--profile", "work"]) as argv:
                profile = tomllib.loads((home / (argv[1] + ".config.toml")).read_text())
                self.assertNotIn(
                    "/external/base-only/SKILL.md", {e["path"] for e in profile["skills"]["config"]}
                )

    def test_default_native_profile_is_preserved_without_explicit_cli_profile(self):
        from codex_bootstrap.config import launch_profile

        home = self.root / "codex-home"
        home.mkdir()
        (home / "config.toml").write_text(
            'profile="work"\n[profiles.work]\nmodel="user-model"\n'
            'skills.config=[{path="/external/work-only/SKILL.md",enabled=false}]\n'
            '[profiles.work.plugins."user@registry"]\nenabled=false\n'
        )
        (self.root / ".codex/integrations.toml").write_text('[integrations]\nmode="coexist"\n')
        with patch.dict(
            os.environ, {"CODEX_HOME": str(home), "CODEX_BOOTSTRAP_INTEGRATION_MODE": ""}
        ):
            with launch_profile(self.root, self.lock, []) as argv:
                profile = tomllib.loads((home / (argv[1] + ".config.toml")).read_text())
                self.assertEqual(profile.get("model"), "user-model")
                self.assertFalse(profile["plugins"]["user@registry"]["enabled"])
                self.assertIn(
                    "/external/work-only/SKILL.md", {e["path"] for e in profile["skills"]["config"]}
                )
