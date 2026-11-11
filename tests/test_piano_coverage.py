import json
import tempfile
import unittest
from pathlib import Path

from suite_support import IsolatedTestCase

from codex_bootstrap.catalog import bundled_candidates
from codex_bootstrap.lifecycle import slot_inputs
from codex_bootstrap.profile import manifest_fingerprint, profile_repo
from codex_bootstrap.proposal import propose
from codex_bootstrap.selection import select
from codex_bootstrap.workspaces import selection_profiles

PIANO_SLOTS = {"midi-python", "led-ws281x", "gpio-python", "platform-raspberry-pi"}


class PianoCoverageTests(IsolatedTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_requirements_normalize_python_names_preserving_constraints_and_sources(self):
        self.write(
            "requirements.txt",
            '  Mido[ports]>=1.3,<2 ; python_version >= "3.11"\n'
            "PYTHON_RTMIDI~=1.5 # native backend\n"
            "rpi_ws281x==5.0.0\nRPi.GPIO>=0.7.1\ngpiozero~=2.0\n",
        )
        profile = profile_repo(self.root)
        self.assertTrue(PIANO_SLOTS.issubset(profile.slots))
        self.assertIn("midi", profile.slots)
        for technology, version in {
            "mido": ">=1.3,<2",
            "python-rtmidi": "~=1.5",
            "rpi-ws281x": "==5.0.0",
            "rpi-gpio": ">=0.7.1",
            "gpiozero": "~=2.0",
        }.items():
            with self.subTest(technology=technology):
                self.assertEqual(profile.technologies[technology], version)
                self.assertEqual(
                    profile.technology_sources[technology],
                    [
                        {
                            "path": "requirements.txt",
                            "version": version,
                            "kind": "declaration",
                            "ecosystem": "pypi",
                            "constraint": version,
                        }
                    ],
                )
        self.assertEqual(profile.slot_technologies["midi-python"], ["mido", "python-rtmidi"])
        self.assertEqual(profile.slot_technologies["led-ws281x"], ["rpi-ws281x"])
        self.assertEqual(profile.slot_technologies["gpio-python"], ["gpiozero", "rpi-gpio"])
        self.assertEqual(
            profile.slot_technologies["platform-raspberry-pi"], ["rpi-gpio", "rpi-ws281x"]
        )

    def test_pyproject_optional_and_poetry_aliases_enable_python_domains(self):
        self.write(
            "pyproject.toml",
            '[project]\nname="piano"\nversion="0.1"\n'
            'dependencies=["MIDO>=1.2,<2", "RPi_GPIO==0.7.1"]\n'
            '[project.optional-dependencies]\nled=["rpi.ws281x>=4,<6"]\n'
            '[tool.poetry.dependencies]\npython="^3.11"\npython_rtmidi="^1.5"\n'
            'gpiozero={version="^2.0", optional=true}\n',
        )
        profile = profile_repo(self.root)
        self.assertTrue(PIANO_SLOTS.issubset(profile.slots))
        self.assertEqual(profile.technologies["python-rtmidi"], "^1.5")
        self.assertEqual(profile.technologies["rpi-ws281x"], ">=4,<6")

    def test_unrelated_python_and_generic_led_names_do_not_imply_hardware(self):
        self.write("requirements.txt", "requests==2.32.0\nled==1.0\ncolorama==0.4.6\n")
        self.write("piano.py", "import mido\nimport rpi_ws281x\nimport RPi.GPIO\n")
        self.write("README.md", "Raspberry Pi MIDI LED lighting project")
        profile = profile_repo(self.root)
        self.assertTrue(PIANO_SLOTS.isdisjoint(profile.slots))
        self.assertNotIn("piano.py", profile.manifests)
        self.assertNotIn("README.md", profile.manifests)

    def test_portable_gpiozero_does_not_assert_raspberry_pi_platform(self):
        self.write("requirements.txt", "gpiozero>=2\n")
        profile = profile_repo(self.root)
        self.assertIn("gpio-python", profile.slots)
        self.assertNotIn("platform-raspberry-pi", profile.slots)
        self.assertNotIn("led-ws281x", profile.slots)

    def test_workspace_selection_does_not_leak_piano_guides_to_web_or_rust(self):
        self.write(
            "piano/requirements.txt",
            "mido>=1.3,<2\npython-rtmidi~=1.5\nrpi_ws281x==5\nRPi.GPIO>=0.7\n",
        )
        self.write("webinterface/package.json", json.dumps({"dependencies": {"react": "^19"}}))
        self.write(
            "backend/Cargo.toml",
            '[package]\nname="backend"\nversion="0.1"\n[dependencies]\nmidir="0.10"\n',
        )
        profiles = selection_profiles(self.root)
        self.assertTrue(PIANO_SLOTS.issubset(profiles["piano"].slots))
        for scope in (".", "webinterface", "backend"):
            self.assertTrue(PIANO_SLOTS.isdisjoint(profiles[scope].slots), scope)
            self.assertNotIn("language-python", profiles[scope].slots)
        self.assertIn("midi", profiles["backend"].slots)

    def test_other_ecosystem_homonyms_and_transitive_locks_do_not_enable_python_guides(self):
        self.write(
            "web/package.json",
            json.dumps(
                {
                    "dependencies": {
                        "mido": "1",
                        "python-rtmidi": "1",
                        "rpi-ws281x": "5",
                        "gpiozero": "2",
                        "rpi-gpio": "1",
                    }
                }
            ),
        )
        self.write(
            "rust/Cargo.toml",
            '[package]\nname="backend"\nversion="0.1"\n[dependencies]\nmido="1"\npython-rtmidi="1"\nrpi-ws281x="5"\ngpiozero="2"\nrpi-gpio="1"\n',
        )
        self.write(
            "web/package-lock.json",
            json.dumps({"packages": {"node_modules/RPi.GPIO": {"version": "0.7.1"}}}),
        )
        for scope, profile in selection_profiles(self.root).items():
            self.assertTrue(PIANO_SLOTS.isdisjoint(profile.slots), scope)

    def test_bundled_piano_guides_are_eligible_for_actual_scoped_profile(self):
        self.write(
            "requirements.txt",
            "mido==1.3.3\npython-rtmidi==1.5.8\nrpi_ws281x==5.0.0\nRPi.GPIO==0.7.1\n",
        )
        profile = profile_repo(self.root)
        winners, rejected = select(bundled_candidates(profile), profile)
        self.assertEqual(rejected, [])
        self.assertTrue(PIANO_SLOTS.issubset({candidate.slot for candidate in winners}))

    def test_dependency_upgrade_changes_only_relevant_domain_refresh_inputs(self):
        self.write("requirements.txt", "mido>=1.3,<2\nrpi_ws281x==4.3.4\n")
        first = profile_repo(self.root)
        old_hashes = manifest_fingerprint(self.root)
        self.write("requirements.txt", "mido>=1.3,<2\nrpi_ws281x==5.0.0\n")
        second = profile_repo(self.root)
        self.assertNotEqual(old_hashes, manifest_fingerprint(self.root))
        self.assertEqual(slot_inputs(first, "midi-python"), slot_inputs(second, "midi-python"))
        for slot in ("led-ws281x", "platform-raspberry-pi"):
            self.assertNotEqual(slot_inputs(first, slot), slot_inputs(second, slot), slot)

    def test_offline_proposal_covers_piano_without_writing_target_or_sibling_scopes(self):
        self.write(
            "piano/requirements.txt",
            "mido~=1.3.3\npython-rtmidi~=1.5.8\nrpi-ws281x~=5.0.0\nRPi.GPIO~=0.7.1\n",
        )
        self.write("webinterface/package.json", '{"dependencies":{"react":"^19"}}')
        self.write("backend/Cargo.toml", '[package]\nname="backend"\nversion="0.1.0"\n')
        before = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        with tempfile.TemporaryDirectory() as cache:
            report = propose(self.root, offline=True, cache_dir=Path(cache))
        self.assertFalse(report["installed"])
        piano = {record["slot"] for record in report["selected"] if record["scope"] == "piano"}
        self.assertTrue(PIANO_SLOTS.issubset(piano))
        for record in report["selected"]:
            if record["slot"] in PIANO_SLOTS:
                self.assertEqual(record["scope"], "piano")
                self.assertEqual(record["source"], "bundled")
        after = {
            path.relative_to(self.root).as_posix(): path.read_bytes()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)
        self.assertFalse(
            any((self.root / name).exists() for name in (".codex", ".agents", ".git", "AGENTS.md"))
        )


if __name__ == "__main__":
    unittest.main()
