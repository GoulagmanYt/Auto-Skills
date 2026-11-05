import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from codex_bootstrap.profile import manifest_paths, profile_repo
from codex_bootstrap.repo_inspection import inspect_repository
from codex_bootstrap.workspaces import workspace_profiles


class RepositoryBoundaryTests(unittest.TestCase):
    def test_redirected_directory_does_not_import_foreign_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root, outside = base / "repo", base / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "package.json").write_text('{"dependencies":{"react":"99.0.0"}}')
            link = root / "linked"
            if os.name == "nt":
                shell = shutil.which("powershell") or shutil.which("pwsh")
                if not shell:
                    self.skipTest("PowerShell junction creation unavailable")
                env = {
                    **os.environ,
                    "AUTO_SKILLS_JUNCTION_LINK": str(link),
                    "AUTO_SKILLS_JUNCTION_TARGET": str(outside),
                }
                created = subprocess.run(
                    [shell, "-NoProfile", "-NonInteractive", "-Command", "-"],
                    input='$ErrorActionPreference="Stop"\nNew-Item -ItemType Junction -Path $env:AUTO_SKILLS_JUNCTION_LINK -Target $env:AUTO_SKILLS_JUNCTION_TARGET | Out-Null\n',
                    env=env,
                    text=True,
                    capture_output=True,
                    timeout=30,
                )
                if created.returncode:
                    self.skipTest("junction creation unavailable")
            else:
                link.symlink_to(outside, target_is_directory=True)
            try:
                diagnostics = []
                self.assertEqual(list(manifest_paths(root, diagnostics=diagnostics)), [])
                self.assertTrue(diagnostics)
                self.assertNotIn("react", profile_repo(root).technologies)
                self.assertNotIn("react", workspace_profiles(root)["."].technologies)
                inspection = inspect_repository(root)
                self.assertNotIn("linked/package.json", inspection["files"])
                self.assertTrue(inspection["diagnostics"])
            finally:
                if link.is_symlink():
                    link.unlink()
                elif link.exists():
                    link.rmdir()
            self.assertTrue((outside / "package.json").is_file())

    def test_git_worktree_and_nested_repository_are_distinct(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source, worktree = base / "source", base / "checkout"
            source.mkdir()
            env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

            def git(*args, cwd=source):
                subprocess.run(
                    ["git", *args], cwd=cwd, env=env, check=True, capture_output=True, timeout=30
                )

            git("init", "-q", "--template=")
            (source / "Cargo.toml").write_text('[package]\nname="example"\nversion="0.1.0"')
            git("add", ".")
            git(
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                "-c",
                "commit.gpgsign=false",
                "commit",
                "-qm",
                "fixture",
            )
            git("worktree", "add", "--detach", str(worktree), "HEAD")
            self.assertTrue((worktree / ".git").is_file())
            self.assertIn("rust", profile_repo(worktree).technologies)
            nested = worktree / "nested"
            nested.mkdir()
            git("init", "-q", "--template=", cwd=nested)
            (nested / "package.json").write_text('{"dependencies":{"react":"^19"}}')
            profile = profile_repo(worktree)
            self.assertNotIn("react", profile.technologies)
            self.assertTrue(any(d["code"] == "submodule-boundary" for d in profile.diagnostics))
