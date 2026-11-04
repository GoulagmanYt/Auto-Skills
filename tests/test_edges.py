import base64
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_bootstrap.bootstrap import bootstrap, recover_transaction
from codex_bootstrap.config import launch_profile
from codex_bootstrap.fs import digest
from codex_bootstrap.token_tools import extract_regular


class EdgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)

    def test_archive_cannot_write_outside_destination(self):
        data = io.BytesIO()
        with tarfile.open(fileobj=data, mode="w:gz") as archive:
            item = tarfile.TarInfo("../escape.txt")
            item.size = 4
            archive.addfile(item, io.BytesIO(b"evil"))
        with self.assertRaises(ValueError):
            extract_regular(data.getvalue(), self.root / "unpack")
        self.assertFalse((self.root / "escape.txt").exists())

    def test_local_resource_links_are_normalized_within_the_skill_only(self):
        from codex_bootstrap.discovery import normalize_resources

        text, files = normalize_resources(
            "Read [rule](rule.md).",
            {
                "rules/rule.md": b"Return to [skill](../SKILL.md).",
            },
        )
        self.assertIn("](rules/rule.md)", text)
        self.assertIn(b"](../SKILL.md)", files["rules/rule.md"])
        with self.assertRaises(ValueError):
            normalize_resources("Read [secret](../../secret.md).", {})

    def test_external_linked_skill_is_disabled_without_following_cycles_forever(self):
        from codex_bootstrap.config import external_skills

        home = self.root / "fake-home"
        catalog = home / "skills"
        catalog.mkdir(parents=True)
        target = self.root / "linked-target"
        target.mkdir()
        skill = target / "SKILL.md"
        skill.write_text("---\nname: linked-skill\ndescription: linked fixture\n---\n")
        try:
            (catalog / "alias").symlink_to(target, target_is_directory=True)
            (target / "cycle").symlink_to(catalog, target_is_directory=True)
        except OSError:
            self.skipTest("symlinks unavailable")
        with patch.dict(os.environ, {"CODEX_HOME": str(home)}):
            self.assertIn(str(skill.resolve()), external_skills(self.root))

    def test_discovery_queries_both_axes_and_preserves_pinned_provenance(self):
        from codex_bootstrap.discovery import discover
        from codex_bootstrap.profile import Profile

        class FixtureGitHub:
            def __init__(self):
                self.queries, self.errors = [], []

            def search(self, kind, query, limit=4):
                self.queries.append({"kind": kind, "query": query})
                return []

            def snapshot(self, repo):
                return (
                    {"license": {"spdx_id": "MIT"}, "stargazers_count": 100},
                    "a" * 40,
                    [
                        {
                            "path": "skills/unit-testing/SKILL.md",
                            "type": "blob",
                            "mode": "100644",
                            "sha": "s",
                            "size": 400,
                        },
                        {
                            "path": "LICENSE",
                            "type": "blob",
                            "mode": "100644",
                            "sha": "l",
                            "size": 3,
                        },
                    ],
                )

            def blob(self, repo, sha, max_size=256000):
                if sha == "l":
                    return b"MIT"
                return b"---\nname: unit-testing\ndescription: Use when testing changed behavior.\n---\nUse the project test runner. Check boundary conditions and failure behavior. Run the targeted suite and verify assertions on public outputs. Keep fixtures deterministic.\n"

        candidates, report = discover(Profile(), FixtureGitHub())
        self.assertTrue(candidates, report)
        self.assertTrue(all(c.commit == "a" * 40 for c in candidates))
        self.assertTrue(all("UPSTREAM-LICENSE" in c.files for c in candidates))
        queries = report["queries"]
        self.assertTrue(any(q["kind"] == "repos" and "GitNexus" in q["query"] for q in queries))
        self.assertTrue(any("reasoning_effort" in q["query"] for q in queries))
        self.assertTrue(any("unit testing" in q["query"] for q in queries))

    def test_recover_interrupted_publish_restores_existing_files(self):
        generated = self.root / ".codex/bin/tool.py"
        generated.parent.mkdir(parents=True)
        generated.write_text("new tool")
        agents = self.root / "AGENTS.md"
        agents.write_text("generated policy")
        journal = {
            "schema_version": 1,
            "files": {
                ".codex/bin/tool.py": {"before": None, "after": digest(generated), "mode": 0o644},
                "AGENTS.md": {
                    "before": base64.b64encode(b"original").decode(),
                    "after": digest(agents),
                    "mode": 0o644,
                },
            },
        }
        (self.root / ".codex/bootstrap-journal.json").write_text(json.dumps(journal))
        recover_transaction(self.root)
        self.assertEqual(agents.read_text(), "original")
        self.assertFalse(generated.exists())
        self.assertFalse((self.root / ".codex/bootstrap-journal.json").exists())

    def test_profile_preserves_user_profile_and_disables_mcp_with_valid_transport(self):
        lock = bootstrap(self.root, offline=True)
        home = self.root / "fake-home"
        home.mkdir()
        (home / "work.config.toml").write_text('model = "custom-model"\n')
        (home / "config.toml").write_text('[mcp_servers.example]\ncommand = "never-run"\n')
        with patch.dict(os.environ, {"CODEX_HOME": str(home)}):
            with launch_profile(self.root, lock, ["exec", "--profile", "work", "hello"]) as args:
                import tomllib

                data = tomllib.loads((home / (args[1] + ".config.toml")).read_text())
                self.assertEqual(data["model"], "custom-model")
                self.assertFalse(data["mcp_servers"]["example"]["enabled"])
                self.assertEqual(data["mcp_servers"]["example"]["command"], "never-run")
                self.assertEqual(args[2:], ["exec", "hello"])

    def test_explicit_program_path_is_not_replaced_by_rtk(self):
        import shutil

        bootstrap(self.root, offline=True)
        # A broken RTK would fail if token-run selected it for an explicit binary path.
        rtk = self.root / ".codex/bin" / ("rtk.exe" if os.name == "nt" else "rtk")
        rtk.write_bytes(b"not executable")
        explicit = Path(shutil.which("git")).resolve()
        # An explicit real Git path must run directly despite the invalid local RTK.
        result = subprocess.run(
            [
                sys.executable,
                str(self.root / ".codex/bin/token-run.py"),
                "--",
                str(explicit),
                "--version",
            ],
            capture_output=True,
            text=True,
            cwd=self.root,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("git version", result.stdout)


if __name__ == "__main__":
    unittest.main()
