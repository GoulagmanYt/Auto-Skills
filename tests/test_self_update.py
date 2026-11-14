"""Self-updates must never turn a network/build failure into a Codex outage."""

import io
import json
import os
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from suite_support import IsolatedTestCase

A, B = "a" * 40, "b" * 40


def archive(files=None):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as output:
        for name, data in (
            files
            or {
                "project/pyproject.toml": b"[project]\nname='codex-repo-auto-bootstrap'\n",
                "project/src/codex_bootstrap/__init__.py": b"",
            }
        ).items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            output.addfile(info, io.BytesIO(data))
    return stream.getvalue()


def wheel(path, version="new"):
    with zipfile.ZipFile(path, "w") as output:
        output.writestr("codex_bootstrap/__init__.py", f"__version__ = {version!r}\n")
        output.writestr("codex_bootstrap/cli.py", "def main():\n    return 0\n")
        output.writestr(
            "codex_repo_auto_bootstrap-1.dist-info/METADATA",
            "Name: codex-repo-auto-bootstrap\nVersion: 1\n",
        )
    return path


class SelfUpdateTests(IsolatedTestCase):
    def test_unpublished_local_revision_does_not_enable_auto_downgrade(self):
        from codex_bootstrap.self_update import source_revision

        (self.home / ".git").mkdir()

        def git(args, **kwargs):
            if "get-url" in args:
                return "https://github.com/GoulagmanYt/Auto-Skills.git\n"
            if "merge-base" in args:
                raise RuntimeError("unpublished revision")
            return A if "rev-parse" in args else ""

        with patch("codex_bootstrap.self_update.command", side_effect=git):
            self.assertIsNone(source_revision(self.home))

    def test_network_timeout_is_a_failure_with_retry_not_a_busy_worker(self):
        from codex_bootstrap.self_update import status, update

        with patch.dict(os.environ, {"CODEX_BOOTSTRAP_OFFLINE": "0"}):
            result = update(
                self.home, fetcher=lambda *a: (_ for _ in ()).throw(TimeoutError()), now=50
            )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(status(self.home)["last_error"], "TimeoutError")
        self.assertEqual(status(self.home)["next_check"], 950)

    def test_malformed_github_object_preserves_installation(self):
        from codex_bootstrap.self_update import update

        original = (self.base / "installation.json").read_bytes()
        with patch.dict(os.environ, {"CODEX_BOOTSTRAP_OFFLINE": "0"}):
            result = update(self.home, fetcher=lambda *a: b'{"object":null}')
        self.assertEqual(result["status"], "failed")
        self.assertEqual((self.base / "installation.json").read_bytes(), original)

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.base = self.home / ".local/share/codex-auto-bootstrap"
        python = self.base / "venv/python"
        python.parent.mkdir(parents=True)
        python.write_bytes(b"managed python")
        import hashlib

        self.record = {
            "version": 2,
            "source_commit": A,
            "base_commit": A,
            "runtime_path": None,
            "python": str(python),
            "files": {"venv/python": hashlib.sha256(python.read_bytes()).hexdigest()},
            "links": {},
            "profiles": {},
            "path": None,
        }
        (self.base / "installation.json").write_text(json.dumps(self.record))

    def test_offline_and_disabled_updates_never_fetch(self):
        from codex_bootstrap.self_update import configure, update

        with patch.dict(os.environ, {"CODEX_BOOTSTRAP_OFFLINE": "1"}):
            self.assertEqual(
                update(self.home, fetcher=lambda *a: self.fail("network"))["status"], "offline"
            )
        configure(self.home, enabled=False)
        with patch.dict(os.environ, {"CODEX_BOOTSTRAP_OFFLINE": "0"}):
            self.assertEqual(
                update(self.home, automatic=True, fetcher=lambda *a: self.fail("network"))[
                    "status"
                ],
                "disabled",
            )

    def test_current_commit_skips_download_and_build(self):
        from codex_bootstrap.self_update import update

        calls = []

        def fetcher(url, limit):
            calls.append(url)
            return json.dumps({"object": {"sha": A}}).encode()

        with patch.dict(os.environ, {"CODEX_BOOTSTRAP_OFFLINE": "0"}):
            result = update(self.home, fetcher=fetcher, builder=lambda *a: self.fail("build"))
        self.assertEqual(result["status"], "current")
        self.assertEqual(len(calls), 1)

    def test_network_failure_preserves_installation_and_backs_off(self):
        from codex_bootstrap.self_update import status, update

        original = (self.base / "installation.json").read_bytes()

        def failing_fetch(*args):
            raise OSError("sensitive credential must not be retained")

        with patch.dict(os.environ, {"CODEX_BOOTSTRAP_OFFLINE": "0"}):
            result = update(self.home, fetcher=failing_fetch, now=1000)
        self.assertEqual(result["status"], "failed")
        self.assertEqual((self.base / "installation.json").read_bytes(), original)
        state = status(self.home)
        self.assertGreater(state["next_check"], 1000)
        self.assertNotIn("sensitive credential", json.dumps(state))

    def test_auto_update_is_rate_limited(self):
        from codex_bootstrap.self_update import update

        with patch.dict(os.environ, {"CODEX_BOOTSTRAP_OFFLINE": "0"}):
            update(
                self.home, fetcher=lambda *a: json.dumps({"object": {"sha": A}}).encode(), now=1000
            )
            result = update(
                self.home, automatic=True, now=1001, fetcher=lambda *a: self.fail("second fetch")
            )
        self.assertEqual(result["status"], "not-due")

    def test_modified_installation_is_not_overwritten_or_downloaded(self):
        from codex_bootstrap.self_update import update

        (self.base / "venv/python").write_bytes(b"user modification")
        with patch.dict(os.environ, {"CODEX_BOOTSTRAP_OFFLINE": "0"}):
            result = update(self.home, fetcher=lambda *a: self.fail("network"))
        self.assertEqual(result["status"], "conflict")

    def test_archive_rejects_path_traversal_and_symlinks(self):
        from codex_bootstrap.self_update import extract_source

        for name in (
            "../escape",
            "project/../../escape",
            "project/C:/escape",
            "project/dir\\escape",
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                extract_source(archive({name: b"x"}), self.home / "stage")
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w:gz") as output:
            info = tarfile.TarInfo("project/link")
            info.type, info.linkname = tarfile.SYMTYPE, "../../outside"
            output.addfile(info)
        with self.assertRaises(ValueError):
            extract_source(stream.getvalue(), self.home / "links")

    def test_unknown_provenance_does_not_enable_automatic_updates(self):
        from codex_bootstrap.self_update import status

        self.record["source_commit"] = None
        (self.base / "installation.json").write_text(json.dumps(self.record))
        self.assertFalse(status(self.home)["enabled"])

    def test_cli_status_does_not_launch_native_codex_or_fetch(self):
        from contextlib import redirect_stdout

        from codex_bootstrap.cli import main

        output = io.StringIO()
        with (
            patch("codex_bootstrap.self_update.fetch", side_effect=AssertionError("network")),
            patch("codex_bootstrap.cli.real_codex", side_effect=AssertionError("native Codex")),
            redirect_stdout(output),
        ):
            self.assertEqual(main(["self-update", "status", "--home", str(self.home)]), 0)
        self.assertEqual(json.loads(output.getvalue())["installed_commit"], A)

    def test_scheduler_ignores_development_checkouts(self):
        from codex_bootstrap.self_update import maybe_schedule_update

        with patch("subprocess.Popen", side_effect=AssertionError("background process")):
            self.assertFalse(maybe_schedule_update(self.home))

    def test_disable_during_build_prevents_automatic_activation(self):
        from codex_bootstrap.self_update import configure, update

        def fetcher(url, limit):
            return (
                json.dumps({"object": {"sha": B}}).encode()
                if url.endswith("heads/main")
                else archive()
            )

        def builder(source, python, work):
            configure(self.home, enabled=False)
            return wheel(work / "built.whl")

        with patch.dict(os.environ, {"CODEX_BOOTSTRAP_OFFLINE": "0"}):
            result = update(self.home, automatic=True, fetcher=fetcher, builder=builder)
        self.assertEqual(result["status"], "disabled")
        self.assertEqual(
            json.loads((self.base / "installation.json").read_text())["source_commit"], A
        )

    def test_duplicate_worker_is_not_started_under_installation_lock(self):
        # A different process cannot enter the same exclusive lock.
        import subprocess

        from codex_bootstrap.runtime_loader import installation_mutex

        with installation_mutex(self.base):
            code = "from codex_bootstrap.self_update import update;import sys,json;print(json.dumps(update(sys.argv[1],automatic=True)))"
            env = dict(os.environ, CODEX_BOOTSTRAP_OFFLINE="0")
            result = subprocess.run(
                [sys.executable, "-B", "-c", code, str(self.home)],
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
            )
        self.assertEqual(json.loads(result.stdout)["status"], "busy")


if __name__ == "__main__":
    unittest.main()
