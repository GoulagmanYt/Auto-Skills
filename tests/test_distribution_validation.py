"""Exercise on-disk ZIP/tar distributions without requiring a network or Codex."""

import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from tools.check_artifacts import PUBLIC_DOCS, REQUIRED_MODULES, ROOT_FILES, check_archive


class DistributionValidationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def wheel(self, extra=None):
        path = self.root / "codex_repo_auto_bootstrap-1.3.0a1-py3-none-any.whl"
        files = {"codex_bootstrap/" + name: b"# public runtime\n" for name in REQUIRED_MODULES}
        files["codex_repo_auto_bootstrap-1.3.0a1.dist-info/entry_points.txt"] = (
            b"[console_scripts]\n"
        )
        files.update(
            {
                "codex_repo_auto_bootstrap-1.3.0a1.dist-info/" + name: b"public\n"
                for name in ("METADATA", "WHEEL", "RECORD")
            }
        )
        files.update(extra or {})
        with zipfile.ZipFile(path, "w") as archive:
            for name, data in files.items():
                archive.writestr(name, data)
        return path

    def sdist(self, extra=None):
        path = self.root / "codex_repo_auto_bootstrap-1.3.0a1.tar.gz"
        files = {"src/codex_bootstrap/" + name: b"# public runtime\n" for name in REQUIRED_MODULES}
        files.update({name: b"public\n" for name in ROOT_FILES})
        files.update({"docs/" + name: b"public\n" for name in PUBLIC_DOCS})
        files.update(
            {
                name: b"public\n"
                for name in (
                    "README.md",
                    "LICENSE",
                    "pyproject.toml",
                    "MANIFEST.in",
                    "install.sh",
                    "install.ps1",
                    "tools/check_artifacts.py",
                    "tools/verify_native_install.py",
                    "docs/compatibility.md",
                )
            }
        )
        files.update(extra or {})
        with tarfile.open(path, "w:gz") as archive:
            for name, data in files.items():
                item = tarfile.TarInfo("codex_repo_auto_bootstrap-1.3.0a1/" + name)
                item.size = len(data)
                archive.addfile(item, io.BytesIO(data))
        return path

    def test_minimal_public_archives_pass(self):
        for path in (self.wheel(), self.sdist()):
            with self.subTest(path=path.name):
                result = check_archive(path)
                self.assertGreater(result["members"], len(REQUIRED_MODULES))

    def test_private_and_unlisted_members_fail_closed(self):
        for name in (
            "reports/private.md",
            ".serena/project.yml",
            "src/codex_bootstrap/__pycache__/cli.pyc",
            "docs/checkpoint.md",
            "unreviewed.txt",
        ):
            with self.subTest(name=name), self.assertRaises(ValueError):
                check_archive(self.sdist({name: b"private"}))

    def test_paths_and_credentials_are_rejected_without_printing_values(self):
        values = [
            "C:" + "/" + "Users/" + "private-person/project",
            "/" + "home/" + "private-person/project",
            "sk-" + "a" * 40,
            "ghp_" + "b" * 40,
            "AKIA" + "C" * 16,
            'api_key="' + "credential" * 5 + '"',
            "-----BEGIN " + "PRIVATE KEY-----",
        ]
        for value in values:
            with self.subTest(value_length=len(value)):
                with self.assertRaises(ValueError) as raised:
                    check_archive(self.wheel({"codex_bootstrap/leak.py": value.encode()}))
                self.assertNotIn(value, str(raised.exception))
                self.assertIn("found in codex_bootstrap/leak.py", str(raised.exception))

    def test_traversal_and_links_are_never_extracted(self):
        with self.assertRaisesRegex(ValueError, "unsafe"):
            check_archive(self.sdist({"../escape.py": b"bad"}))
        path = self.root / "link.tar.gz"
        with tarfile.open(path, "w:gz") as archive:
            item = tarfile.TarInfo("package/src/link.py")
            item.type = tarfile.SYMTYPE
            item.linkname = "outside"
            archive.addfile(item)
        with self.assertRaisesRegex(ValueError, "link"):
            check_archive(path)

    def test_missing_runtime_module_is_reported(self):
        path = self.wheel()
        with zipfile.ZipFile(path) as archive:
            files = {
                name: archive.read(name)
                for name in archive.namelist()
                if name != "codex_bootstrap/cli.py"
            }
        with zipfile.ZipFile(path, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        with self.assertRaisesRegex(
            ValueError, "required distribution files missing: codex_bootstrap/cli.py"
        ):
            check_archive(path)

    def test_missing_wheel_metadata_is_reported(self):
        path = self.root / "empty.whl"
        with zipfile.ZipFile(path, "w"):
            pass
        with self.assertRaisesRegex(ValueError, "metadata directory"):
            check_archive(path)

    def test_binary_and_duplicate_members_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "binary"):
            check_archive(self.wheel({"codex_bootstrap/leak.py": b"\xff"}))
        path = self.wheel()
        import warnings

        with warnings.catch_warnings(), zipfile.ZipFile(path, "a") as archive:
            warnings.simplefilter("ignore", UserWarning)
            archive.writestr("codex_bootstrap/cli.py", b"duplicate")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            check_archive(path)


if __name__ == "__main__":
    unittest.main()
