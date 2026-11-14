"""Exercise activation and crash recovery with a real isolated Python venv."""

import json
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from unittest.mock import patch

from suite_support import IsolatedTestCase
from test_self_update import A, B, wheel


class SelfUpdateRuntimeTests(IsolatedTestCase):
    def setUp(self):
        from codex_bootstrap import installer

        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.base = self.home / installer.BASE
        self.profile = self.home / ".profile"
        self.profile.write_text("# user configuration\n")

        def create(base, source):
            venv.EnvBuilder(with_pip=False).create(base / "venv")
            python = (
                base / "venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
            )
            site = Path(
                subprocess.check_output(
                    [
                        str(python),
                        "-I",
                        "-c",
                        "import sysconfig;print(sysconfig.get_path('purelib'))",
                    ],
                    text=True,
                ).strip()
            )
            package = site / "codex_bootstrap"
            package.mkdir()
            (package / "__init__.py").write_text("__version__='old'\n")
            (package / "cli.py").write_text("identity='old'\n")
            return python

        installer.install(
            home=self.home,
            real=Path(sys.executable),
            source=self.home,
            platform="posix",
            profiles=[self.profile],
            package_install=create,
            revision=A,
        )
        self.record = json.loads((self.base / "installation.json").read_text())
        self.python = self.record["python"]
        self.work = self.home / "work"
        self.work.mkdir()

    def version(self):
        return subprocess.check_output(
            [
                self.python,
                "-I",
                "-B",
                "-c",
                "import codex_bootstrap;print(codex_bootstrap.__version__)",
            ],
            text=True,
        ).strip()

    def test_next_process_uses_new_package_and_rollback_restores_base(self):
        from codex_bootstrap.installer import _validate_files
        from codex_bootstrap.self_update import publish_wheel, rollback, status

        profile = self.profile.read_bytes()
        self.assertEqual(self.version(), "old")
        publish_wheel(self.base, self.record, wheel(self.work / "new.whl"), B, self.work)
        self.assertEqual(self.version(), "new")
        self.assertEqual(self.profile.read_bytes(), profile)
        record = json.loads((self.base / "installation.json").read_text())
        self.assertEqual(_validate_files(self.base, record["files"], record["links"]), [])
        self.assertEqual(rollback(self.home)["status"], "rolled-back")
        self.assertEqual(self.version(), "old")
        self.assertFalse(status(self.home)["enabled"])

    def test_existing_session_children_keep_base_and_versioned_runtime(self):
        from codex_bootstrap.self_update import publish_wheel

        child = "import codex_bootstrap;print(codex_bootstrap.__version__)"
        script = (
            "import subprocess,sys;print('ready',flush=True);input();"
            f"subprocess.run([sys.executable,'-I','-B','-c',{child!r}],check=True)"
        )
        for old, revision, new in [("old", B, "new"), ("new", "c" * 40, "newer")]:
            with self.subTest(runtime=old):
                process = subprocess.Popen(
                    [self.python, "-I", "-B", "-c", script],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    text=True,
                )
                try:
                    self.assertEqual(process.stdout.readline().strip(), "ready")
                    work = self.work / revision
                    work.mkdir()
                    record = json.loads((self.base / "installation.json").read_text())
                    publish_wheel(self.base, record, wheel(work / "new.whl", new), revision, work)
                    output, _ = process.communicate("\n", timeout=10)
                    self.assertEqual(output.strip(), old)
                    self.assertEqual(self.version(), new)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate()

    def test_deleted_runtime_file_blocks_reuse_and_rollback(self):
        import os

        from codex_bootstrap.self_update import publish_wheel, rollback, update

        publish_wheel(self.base, self.record, wheel(self.work / "new.whl"), B, self.work)
        self.assertEqual(rollback(self.home)["status"], "rolled-back")
        (self.base / "venv/versions" / B / "codex_bootstrap/cli.py").unlink()
        with patch.dict(os.environ, {"CODEX_BOOTSTRAP_OFFLINE": "0"}):
            result = update(
                self.home, fetcher=lambda *a: json.dumps({"object": {"sha": B}}).encode()
            )
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(rollback(self.home)["status"], "conflict")
        self.assertEqual(self.version(), "old")

    def test_successful_update_pipeline_activates_sha_and_uninstalls_all_versions(self):
        import os

        from test_self_update import archive

        from codex_bootstrap.installer import uninstall
        from codex_bootstrap.self_update import update

        calls = []

        def fetcher(url, limit):
            calls.append(url)
            return json.dumps({"object": {"sha": B}}).encode() if len(calls) == 1 else archive()

        with patch.dict(os.environ, {"CODEX_BOOTSTRAP_OFFLINE": "0"}):
            result = update(
                self.home, fetcher=fetcher, builder=lambda s, p, w: wheel(w / "new.whl")
            )
        self.assertEqual(result["status"], "updated")
        self.assertTrue(calls[1].endswith("/tar.gz/" + B))
        self.assertEqual(self.version(), "new")
        uninstall(home=self.home)
        self.assertFalse((self.base / "venv").exists())
        self.assertEqual(self.profile.read_text(), "# user configuration\n")

    def test_running_process_keeps_its_original_package(self):
        from codex_bootstrap.self_update import publish_wheel

        process = subprocess.Popen(
            [
                self.python,
                "-I",
                "-B",
                "-c",
                "import codex_bootstrap;print(codex_bootstrap.__version__,flush=True);input();from codex_bootstrap.cli import identity;print(identity,flush=True)",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertEqual(process.stdout.readline().strip(), "old")
            publish_wheel(self.base, self.record, wheel(self.work / "new.whl"), B, self.work)
            output, _ = process.communicate("continue\n", timeout=10)
            self.assertEqual(output.strip(), "old")
            self.assertEqual(self.version(), "new")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            process.stdout.close()

    def crash_before_publication(self):
        from codex_bootstrap import self_update

        original = self_update.atomic_write

        def fail(path, data, **kwargs):
            if path == self.base / "installation.json":
                raise OSError("simulated process interruption")
            return original(path, data, **kwargs)

        with (
            patch("codex_bootstrap.self_update.atomic_write", side_effect=fail),
            self.assertRaises(OSError),
        ):
            self_update.publish_wheel(
                self.base, self.record, wheel(self.work / "new.whl"), B, self.work
            )

    def test_interrupted_activation_recovers_without_changing_original_version(self):
        from codex_bootstrap.self_update import recover_pending

        self.crash_before_publication()
        self.assertEqual(self.version(), "old")
        recover_pending(self.base)
        self.assertFalse((self.base / "venv/versions" / B).exists())
        self.assertEqual(json.loads((self.base / "installation.json").read_text()), self.record)

    def test_recovery_does_not_delete_modified_pending_files(self):
        from codex_bootstrap.self_update import recover_pending

        self.crash_before_publication()
        path = self.base / "venv/versions" / B / "codex_bootstrap/cli.py"
        path.write_text("# user edit\n")
        with self.assertRaises(ValueError):
            recover_pending(self.base)
        self.assertTrue(path.exists())
