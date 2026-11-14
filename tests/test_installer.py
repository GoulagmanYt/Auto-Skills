import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from suite_support import IsolatedTestCase

from codex_bootstrap import installer


class Registry:
    def __init__(self, value=None):
        self.value = value

    def read_path(self):
        return self.value

    def write_path(self, value, kind):
        self.value = (value, kind)

    def delete_path(self):
        self.value = None

    def notify(self):
        pass


class InstallerTests(IsolatedTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve()
        self.real = self.home / "native-codex"
        self.real.write_bytes(b"native executable")
        self.profile = self.home / ".profile"
        self.original = b"\xef\xbb\xbf# user profile\r\nexport USER_SETTING=yes\r\n\r\n"
        self.profile.write_bytes(self.original)
        self.mode = self.profile.stat().st_mode & 0o777

    def install(self, **kwargs):
        return installer.install(
            home=self.home,
            real=self.real,
            source=self.home,
            platform="posix",
            profiles=[self.profile],
            package_install=lambda base, source: self.real,
            **kwargs,
        )

    def test_install_preserves_codex_launcher_alias(self):
        requested, canonical = self.ancestor_alias_home()
        (canonical / "codex.exe").write_bytes(b"native executable")
        launcher = requested / "codex.exe"
        record = installer.install(
            home=self.home,
            real=launcher,
            source=self.home,
            platform="posix",
            profiles=[],
            package_install=lambda base, source: self.real,
        )
        self.assertEqual(json.loads(record.read_text())["real_codex"], str(launcher))

        from codex_bootstrap.cli import real_codex

        with patch.dict(os.environ, {"CODEX_BOOTSTRAP_REAL_CODEX": str(launcher)}):
            self.assertEqual(real_codex(), [str(launcher)])

    def ancestor_alias_home(self):
        parent = self.home / "canonical-parent"
        parent.mkdir()
        home = parent / "home"
        home.mkdir()
        alias = self.home / "ancestor-alias"
        if os.name == "nt":
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(alias), str(parent)],
                capture_output=True,
                check=False,
            )
            if result.returncode:
                self.skipTest("directory junctions unavailable")
            self.addCleanup(alias.rmdir)
        else:
            try:
                alias.symlink_to(parent, target_is_directory=True)
            except OSError:
                self.skipTest("directory symlinks unavailable")
            self.addCleanup(alias.unlink)
        return alias / "home", home

    def test_install_maps_profile_from_requested_ancestor_alias_to_canonical_home(self):
        requested, canonical = self.ancestor_alias_home()
        profile = canonical / ".profile"
        profile.write_bytes(self.original)
        options = dict(
            home=requested,
            real=self.real,
            source=self.home,
            platform="posix",
            profiles=[requested / ".profile"],
            package_install=lambda base, source: self.real,
        )
        installer.install(**options)
        installer.install(**options)
        self.assertFalse(installer.uninstall(home=requested, platform="posix")["conflicts"])
        self.assertEqual(profile.read_bytes(), self.original)
        self.assertFalse((canonical / installer.BASE).exists())

    def test_scanner_and_link_target_accept_only_ancestor_aliases(self):
        requested, canonical = self.ancestor_alias_home()
        base = requested / "owned-installation"
        (base / "venv/lib").mkdir(parents=True)
        (base / "venv/lib/package.py").write_bytes(b"owned")
        files, links, _ = installer._scan_tree(base)
        self.assertEqual(set(files), {"venv/lib/package.py"})
        self.assertEqual(links, {})
        target = installer._link_target(base, base / "venv/lib64", "lib")
        self.assertEqual(target, canonical / "owned-installation/venv/lib")
        with self.assertRaises(ValueError):
            installer._link_target(base, base / "venv/lib64", str(self.home))

    def test_ancestor_alias_does_not_allow_redirected_owned_root_or_children(self):
        requested, canonical = self.ancestor_alias_home()
        outside = self.home / "outside-owned-tree"
        outside.mkdir()
        (outside / "keep.txt").write_bytes(b"untouched")
        base = canonical / "owned-installation"
        base.mkdir()
        redirect = base / "venv"
        if os.name == "nt":
            result = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(redirect), str(outside)],
                capture_output=True,
                check=False,
            )
            if result.returncode:
                self.skipTest("directory junctions unavailable")
            self.addCleanup(redirect.rmdir)
        else:
            redirect.symlink_to(outside, target_is_directory=True)
            self.addCleanup(redirect.unlink)
        with self.assertRaises(ValueError):
            installer._scan_tree(requested / "owned-installation")
        with self.assertRaises(ValueError):
            installer._scan_tree(requested / "owned-installation/venv")
        self.assertEqual((outside / "keep.txt").read_bytes(), b"untouched")

    def test_update_retains_original_bytes_and_uninstall_is_idempotent(self):
        record = self.install()
        self.install()
        result = installer.uninstall(home=self.home, platform="posix")
        self.assertFalse(result["conflicts"])
        self.assertEqual(self.profile.read_bytes(), self.original)
        self.assertEqual(self.profile.stat().st_mode & 0o777, self.mode)
        self.assertFalse(record.exists())
        self.assertEqual(installer.uninstall(home=self.home)["status"], "not-installed")
        self.assertEqual(self.real.read_bytes(), b"native executable")

    def test_surgical_profile_removal_keeps_later_edits(self):
        self.install()
        with self.profile.open("ab") as stream:
            stream.write(b"\n# later user setting\r\n")
        installer.uninstall(home=self.home, platform="posix")
        self.assertEqual(self.profile.read_bytes(), self.original + b"\n# later user setting\r\n")

    def test_update_does_not_absorb_later_user_edits_into_original_snapshot(self):
        self.install()
        with self.profile.open("ab") as stream:
            stream.write(b"# user added after install\r\n")
        self.install()
        installer.uninstall(home=self.home, platform="posix")
        self.assertEqual(
            self.profile.read_bytes(), self.original + b"# user added after install\r\n"
        )

    def test_dry_run_preserves_profile_record_and_registry(self):
        record = self.install()
        before = self.profile.read_bytes()
        result = installer.uninstall(home=self.home, platform="posix", dry_run=True)
        self.assertEqual(result["status"], "dry-run")
        self.assertEqual(self.profile.read_bytes(), before)
        self.assertTrue(record.exists())

    def test_snapshot_retains_all_permission_bits(self):
        from types import SimpleNamespace
        from unittest.mock import patch

        from codex_bootstrap.repository_uninstall import snapshot

        original_stat = Path.stat

        def with_special_permissions(path, *args, **kwargs):
            actual = original_stat(path, *args, **kwargs)
            if path == self.profile:
                return SimpleNamespace(st_mode=actual.st_mode | 0o2000)
            return actual

        with patch.object(Path, "stat", with_special_permissions):
            entry = snapshot(self.profile)
        self.assertTrue(entry["mode"] & 0o2000)

    def test_windows_update_preserves_later_path_when_entry_was_removed(self):
        registry = Registry(("C:\\original", 1))
        options = dict(
            home=self.home,
            real=self.real,
            source=self.home,
            platform="nt",
            profiles=[],
            registry=registry,
            package_install=lambda base, source: self.real,
        )
        installer.install(**options)
        registry.value = ("C:\\replacement;C:\\later", 2)
        installer.install(**options)
        installer.uninstall(home=self.home, platform="nt", registry=registry)
        self.assertEqual(registry.value, ("C:\\replacement;C:\\later", 2))

    def test_dry_run_and_modified_wrapper_leave_all_files_untouched(self):
        record = self.install()
        shim = record.parent / "bin/codex"
        shim.write_bytes(b"user replacement")
        installed_profile = self.profile.read_bytes()
        result = installer.uninstall(home=self.home, platform="posix")
        self.assertTrue(result["conflicts"])
        self.assertEqual(self.profile.read_bytes(), installed_profile)
        self.assertTrue(record.exists())

    def test_windows_path_restores_original_type_or_preserves_later_changes(self):
        registry = Registry(("C:\\original;;%TOOLS%", 1))
        installer.install(
            home=self.home,
            real=self.real,
            source=self.home,
            platform="nt",
            profiles=[self.profile],
            registry=registry,
            package_install=lambda base, source: self.real,
        )
        self.assertEqual(registry.value[1], 2)
        installer.uninstall(home=self.home, platform="nt", registry=registry)
        self.assertEqual(registry.value, ("C:\\original;;%TOOLS%", 1))
        installer.install(
            home=self.home,
            real=self.real,
            source=self.home,
            platform="nt",
            profiles=[],
            registry=registry,
            package_install=lambda base, source: self.real,
        )
        registry.value = (registry.value[0] + ";C:\\later", 2)
        installer.uninstall(home=self.home, platform="nt", registry=registry)
        self.assertEqual(registry.value, ("C:\\original;;%TOOLS%;C:\\later", 2))

    def test_unowned_base_and_redirected_profile_are_rejected(self):
        base = self.home / ".local/share/codex-auto-bootstrap"
        base.mkdir(parents=True)
        (base / "personal.txt").write_text("keep")
        with self.assertRaisesRegex(ValueError, "unowned"):
            self.install()

    def test_redirected_profile_is_rejected_before_installation(self):
        target = self.home / "user-file"
        target.write_text("keep")
        self.profile.unlink()
        try:
            self.profile.symlink_to(target)
        except OSError:
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ValueError, "redirected"):
            self.install()
        self.assertEqual(target.read_text(), "keep")

    def test_absent_windows_path_is_removed_and_preexisting_wrapper_entry_is_retained(self):
        registry = Registry()
        options = dict(
            home=self.home,
            real=self.real,
            source=self.home,
            platform="nt",
            profiles=[],
            registry=registry,
            package_install=lambda base, source: self.real,
        )
        installer.install(**options)
        installer.uninstall(home=self.home, platform="nt", registry=registry)
        self.assertIsNone(registry.value)
        original = (str(self.home / ".local/share/codex-auto-bootstrap/bin") + ";C:\\mine", 1)
        registry.value = original
        installer.install(**options)
        installer.uninstall(home=self.home, platform="nt", registry=registry)
        self.assertEqual(registry.value, original)

    def test_legacy_record_does_not_invent_original_registry_or_delete_artifacts(self):
        base = self.home / ".local/share/codex-auto-bootstrap"
        base.mkdir(parents=True)
        (base / "installation.json").write_text(
            json.dumps({"version": 1, "real_codex": str(self.real), "bin": str(base / "bin")})
        )
        registry = Registry(("C:\\unknown", 1))
        result = installer.uninstall(home=self.home, platform="nt", registry=registry)
        self.assertTrue(result["conflicts"])
        self.assertEqual(registry.value, ("C:\\unknown", 1))

    def test_cli_install_and_uninstall_accept_explicit_home(self):
        from unittest.mock import patch

        from codex_bootstrap.cli import main

        with patch("codex_bootstrap.installer.install") as action:
            self.assertEqual(
                main(["install", "--home", str(self.home), "--real", str(self.real)]), 0
            )
            action.assert_called_once_with(home=self.home, real=self.real)
        with patch(
            "codex_bootstrap.installer.uninstall",
            return_value={"status": "dry-run", "conflicts": []},
        ) as action:
            self.assertEqual(main(["uninstall", "--home", str(self.home), "--dry-run"]), 0)
            action.assert_called_once_with(home=self.home, dry_run=True)

    def test_failed_first_package_install_rolls_back_then_allows_retry(self):
        def fail(base, source):
            path = base / "venv/partial"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"incomplete package")
            raise RuntimeError("injected package install failure")

        with self.assertRaisesRegex(RuntimeError, "injected"):
            installer.install(
                home=self.home,
                real=self.real,
                source=self.home,
                platform="posix",
                profiles=[self.profile],
                package_install=fail,
            )
        self.assertFalse((self.home / installer.BASE).exists())
        self.assertEqual(self.profile.read_bytes(), self.original)
        self.install()
        self.assertFalse(installer.uninstall(home=self.home, platform="posix")["conflicts"])
        self.assertEqual(self.profile.read_bytes(), self.original)

    def test_failed_upgrade_restores_previous_owned_files_and_record(self):
        record = self.install()
        original_record = record.read_bytes()
        original_shim = (record.parent / "bin/codex").read_bytes()
        installed_profile = self.profile.read_bytes()

        def fail(base, source):
            (base / "bin/codex").write_bytes(b"partial replacement")
            path = base / "venv/new/partial"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"new package")
            raise RuntimeError("injected upgrade failure")

        with self.assertRaisesRegex(RuntimeError, "injected"):
            installer.install(
                home=self.home,
                real=self.real,
                source=self.home,
                platform="posix",
                profiles=[self.profile],
                package_install=fail,
            )
        self.assertEqual(record.read_bytes(), original_record)
        self.assertEqual((record.parent / "bin/codex").read_bytes(), original_shim)
        self.assertFalse((record.parent / "venv").exists())
        self.assertEqual(self.profile.read_bytes(), installed_profile)
        self.assertFalse(installer.uninstall(home=self.home, platform="posix")["conflicts"])

    def test_link_targets_are_confined_to_venv_and_cannot_point_to_ancestors(self):
        base = self.home / installer.BASE
        (base / "venv/lib").mkdir(parents=True)
        path = base / "venv/lib64"
        self.assertEqual(installer._link_target(base, path, "lib"), base / "venv/lib")
        for target in (str(self.home), "..", ".", "lib64"):
            with self.assertRaises(ValueError):
                installer._link_target(base, path, target)

    def test_tree_scanner_records_link_without_traversing_it(self):
        from unittest.mock import patch

        base = self.home / installer.BASE
        (base / "venv/lib").mkdir(parents=True)
        link = base / "venv/lib64"
        link.mkdir()
        (link / "must-not-be-followed").write_bytes(b"outside the scanned view")
        original_is_symlink = Path.is_symlink

        def is_link(path):
            return path == link or original_is_symlink(path)

        with patch.object(Path, "is_symlink", is_link), patch("os.readlink", return_value="lib"):
            files, links, _ = installer._scan_tree(base)
        self.assertEqual(files, {})
        self.assertEqual(links, {"venv/lib64": "lib"})

    def test_registry_failure_restores_profiles_and_first_installation_tree(self):
        class FailingRegistry(Registry):
            def write_path(self, value, kind):
                raise RuntimeError("injected registry failure")

        registry = FailingRegistry(("C:\\original", 1))
        with self.assertRaisesRegex(RuntimeError, "injected registry"):
            installer.install(
                home=self.home,
                real=self.real,
                source=self.home,
                platform="nt",
                profiles=[self.profile],
                registry=registry,
                package_install=lambda base, source: self.real,
            )
        self.assertEqual(self.profile.read_bytes(), self.original)
        self.assertFalse((self.home / installer.BASE).exists())
        self.assertEqual(registry.value, ("C:\\original", 1))

    def test_internal_venv_link_has_explicit_ownership_and_unlinks_safely(self):
        base = self.home / installer.BASE
        (base / "venv/lib").mkdir(parents=True)
        link = base / "venv/lib64"
        try:
            link.symlink_to("lib", target_is_directory=True)
        except OSError:
            self.skipTest("symlinks unavailable")
        # Package callback creates the standard link, after the ownership check.
        link.unlink()
        (base / "venv/lib").rmdir()
        (base / "venv").rmdir()
        base.rmdir()

        def package(base, source):
            target = base / "venv/lib"
            target.mkdir(parents=True)
            (target / "package.py").write_bytes(b"owned")
            (base / "venv/lib64").symlink_to("lib", target_is_directory=True)
            return self.real

        record = installer.install(
            home=self.home,
            real=self.real,
            source=self.home,
            platform="posix",
            profiles=[],
            package_install=package,
        )
        state = json.loads(record.read_bytes())
        self.assertEqual(state["links"], {"venv/lib64": "lib"})
        installer.install(
            home=self.home,
            real=self.real,
            source=self.home,
            platform="posix",
            profiles=[],
            package_install=lambda base, source: self.real,
        )
        self.assertFalse(installer.uninstall(home=self.home, platform="posix")["conflicts"])
        self.assertFalse(base.exists())

    def test_actual_stdlib_venv_can_install_update_and_uninstall(self):
        import sys
        import venv

        def package(base, source):
            venv.EnvBuilder(with_pip=False).create(base / "venv")
            return Path(sys.executable)

        options = dict(
            home=self.home,
            real=self.real,
            source=self.home,
            platform="posix",
            profiles=[],
            package_install=package,
        )
        record = installer.install(**options)
        first = json.loads(record.read_bytes())
        if sys.platform.startswith("linux"):
            self.assertEqual(first["links"]["venv/lib64"], "lib")
        installer.install(**options)
        self.assertFalse(installer.uninstall(home=self.home, platform="posix")["conflicts"])
        self.assertFalse(record.parent.exists())


if __name__ == "__main__":
    unittest.main()
