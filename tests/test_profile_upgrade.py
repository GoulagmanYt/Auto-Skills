import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from suite_support import IsolatedTestCase

from codex_bootstrap.catalog import bundled_candidates
from codex_bootstrap.profile import profile_repo


class ProfileUpgradeTests(IsolatedTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, name, value):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")

    def test_config_detection_preserves_explicit_versions_and_all_sources(self):
        self.write("package.json", json.dumps({"devDependencies": {"vite": "^6.0"}}))
        self.write("vite.config.ts", "export default {}")
        p = profile_repo(self.root)
        self.assertEqual(p.technologies["vite"], "^6.0")
        self.assertEqual(
            {entry["path"] for entry in p.technology_sources["vite"]},
            {"package.json", "vite.config.ts"},
        )

    def test_actual_distinct_declarations_still_report_multiple(self):
        self.write("a/package.json", '{"dependencies":{"react":"^18"}}')
        self.write("b/package.json", '{"dependencies":{"react":"^19"}}')
        p = profile_repo(self.root)
        self.assertEqual(p.technologies["react"], "multiple")
        self.assertEqual(len(p.technology_sources["react"]), 2)

    def test_lock_resolution_is_separate_from_declared_range(self):
        self.write("package.json", '{"dependencies":{"react":"^19.0.0"}}')
        self.write(
            "package-lock.json",
            json.dumps(
                {
                    "lockfileVersion": 3,
                    "packages": {
                        "": {"dependencies": {"react": "^19.0.0"}},
                        "node_modules/react": {"version": "19.1.0"},
                        "node_modules/thing/node_modules/react": {"version": "18.3.1"},
                    },
                }
            ),
        )
        self.write(
            "Cargo.toml", '[package]\nname="app"\nversion="0.1.0"\n[dependencies]\ncpal="0.15"'
        )
        self.write("Cargo.lock", 'version=3\n[[package]]\nname="cpal"\nversion="0.15.3"')
        p = profile_repo(self.root)
        self.assertEqual(p.technologies["react"], "^19.0.0")
        self.assertEqual(p.resolved_versions["react"], ["18.3.1", "19.1.0"])
        self.assertEqual(p.technologies["cpal"], "0.15")
        self.assertEqual(p.resolved_versions["cpal"], ["0.15.3"])
        self.assertTrue(any(s["kind"] == "lock" for s in p.technology_sources["cpal"]))

    def test_runtime_files_provide_versions_without_conflicting_with_constraints(self):
        self.write("Cargo.toml", '[package]\nname="app"\nversion="0.1.0"\nrust-version="1.80"')
        self.write("rust-toolchain.toml", '[toolchain]\nchannel="1.83.0"')
        self.write("package.json", '{"engines":{"node":">=20"}}')
        self.write(".nvmrc", "22.11.0\n")
        self.write("pyproject.toml", '[project]\nname="app"\nrequires-python=">=3.11"')
        self.write(".python-version", "3.12.7\n")
        p = profile_repo(self.root)
        for tech, declared, resolved in (
            ("rust", "1.80", "1.83.0"),
            ("node", ">=20", "22.11.0"),
            ("python", ">=3.11", "3.12.7"),
        ):
            self.assertEqual(p.technologies[tech], declared)
            self.assertIn(resolved, p.resolved_versions[tech])

    def test_runtime_only_project_has_language_version(self):
        self.write("rust-toolchain.toml", '[toolchain]\nchannel="stable"')
        p = profile_repo(self.root)
        self.assertEqual(p.technologies.get("rust"), "stable")
        self.assertIn("language-rust", p.slots)

    def test_audio_desktop_frontend_domains_have_bundled_rules_and_slot_evidence(self):
        self.write(
            "Cargo.toml",
            """[package]
name="desktop-app"
version="0.1.0"
keywords=["rtp-midi", "osc"]
[dependencies]
tauri="2"
cpal={version="0.15",features=["asio"]}
midir="0.10"
vst3="0.1"
windows-sys="0.59"
tokio={version="1",features=["process"]}
""",
        )
        self.write(
            "package.json",
            json.dumps(
                {
                    "dependencies": {
                        "@tauri-apps/api": "^2",
                        "react": "^19",
                        "zustand": "^5",
                        "react-router-dom": "^7",
                    },
                    "devDependencies": {
                        "vite": "^6",
                        "vitest": "^3",
                        "@testing-library/react": "^16",
                    },
                }
            ),
        )
        p = profile_repo(self.root)
        expected = {
            "framework-tauri",
            "realtime-audio",
            "audio-cpal",
            "audio-asio",
            "midi",
            "rtp-midi",
            "osc",
            "audio-plugin-vst",
            "native-windows",
            "process-workers",
            "build-vite",
            "test-vitest",
            "test-testing-library",
            "frontend-state",
            "frontend-routing",
        }
        self.assertTrue(expected <= set(p.slots), expected - set(p.slots))
        self.assertEqual(p.technologies["tauri"], "2")
        self.assertEqual(p.technologies["tauri-api"], "^2")
        self.assertIn("cpal", p.slot_technologies["realtime-audio"])
        candidates = bundled_candidates(p)
        self.assertEqual({c.slot for c in candidates}, set(p.slots))
        for candidate in candidates:
            self.assertGreater(len(candidate.body), 120)

    def test_generic_async_dependency_does_not_imply_audio_or_process_workers(self):
        self.write("Cargo.toml", '[dependencies]\ntokio="1"')
        self.write("main.rs", "// cpal asio midi vst rtp-midi")
        p = profile_repo(self.root)
        self.assertFalse(
            {"realtime-audio", "audio-asio", "rtp-midi", "process-workers"} & set(p.slots)
        )

    def test_general_slot_evidence_tracks_relevant_technologies_only(self):
        self.write(
            "package.json", '{"devDependencies":{"vite":"^6","vitest":"^3","typescript":"^5"}}'
        )
        self.write(".nvmrc", "22")
        p = profile_repo(self.root)
        self.assertIn("vitest", p.slot_technologies["unit-testing"])
        self.assertIn("javascript", p.slot_technologies["unit-testing"])
        self.assertIn("node", p.slot_technologies["build"])
        self.assertIn("vite", p.slot_technologies["build"])
        self.assertEqual(set(p.slot_technologies["architecture"]), set(p.technologies))
        self.assertEqual(p.slot_technologies.get("token-prompt-cache", []), [])

    def test_cargo_bare_versions_expose_caret_constraint_with_raw_provenance(self):
        self.write("Cargo.toml", '[dependencies]\ntauri="2.0"\ncpal="0.15"')
        p = profile_repo(self.root)
        self.assertEqual(p.technologies["tauri"], "2.0")
        tauri = p.technology_sources["tauri"][0]
        self.assertEqual(tauri["version"], "2.0")
        self.assertEqual(tauri.get("ecosystem"), "cargo")
        self.assertEqual(tauri.get("constraint"), "^2.0")
        self.assertEqual(p.technology_sources["cpal"][0].get("constraint"), "^0.15")

    def test_available_tools_reports_installed_native_and_host_executables(self):
        installed = {"gh", "cmake", "ninja", "clang", "powershell", "pwsh", "bash"}
        with patch(
            "codex_bootstrap.profile.shutil.which",
            side_effect=lambda tool: "/bin/" + tool if tool in installed else None,
        ):
            p = profile_repo(self.root)
        self.assertEqual(set(p.available_tools), installed)

    def test_windows_job_object_feature_identifies_process_workers(self):
        self.write(
            "Cargo.toml",
            '[dependencies]\nwindows={version="0.59",features=["Win32_System_JobObjects"]}',
        )
        p = profile_repo(self.root)
        self.assertIn("process-workers", p.slots)
        self.assertIn("windows", p.slot_technologies["process-workers"])

    def test_lock_only_transitives_do_not_enter_detected_technologies_or_slots(self):
        self.write("Cargo.toml", '[dependencies]\nserde="1"')
        self.write(
            "Cargo.lock",
            'version=3\n[[package]]\nname="serde"\nversion="1.0.0"\n[[package]]\nname="cpal"\nversion="0.15.3"',
        )
        self.write("package.json", '{"dependencies":{"react":"^19"}}')
        self.write(
            "package-lock.json",
            json.dumps(
                {
                    "packages": {
                        "node_modules/react": {"version": "19.1.0"},
                        "node_modules/vite": {"version": "6.0.0"},
                    }
                }
            ),
        )
        p = profile_repo(self.root)
        self.assertEqual(set(p.technologies), {"rust", "serde", "javascript", "react"})
        self.assertNotIn("realtime-audio", p.slots)
        self.assertNotIn("build-vite", p.slots)
        self.assertNotIn("cpal", p.slot_technologies["architecture"])
        self.assertEqual(p.resolved_versions["cpal"], ["0.15.3"])
        self.assertEqual(p.technology_sources["vite"][0]["kind"], "lock")

    def test_tauri_components_preserve_distinct_backend_api_and_cli_versions(self):
        self.write("Cargo.toml", '[dependencies]\ntauri="2.11.5"')
        self.write(
            "package.json",
            '{"dependencies":{"@tauri-apps/api":"^2.11.1"},"devDependencies":{"@tauri-apps/cli":"^2.11.4"}}',
        )
        p = profile_repo(self.root)
        self.assertEqual(p.technologies["tauri"], "2.11.5")
        self.assertEqual(p.technologies["tauri-api"], "^2.11.1")
        self.assertEqual(p.technologies["tauri-cli"], "^2.11.4")
        self.assertEqual(p.technology_sources["tauri-api"][0]["version"], "^2.11.1")
        self.assertEqual(
            set(p.slot_technologies["framework-tauri"]), {"tauri", "tauri-api", "tauri-cli"}
        )

    def test_frontend_only_tauri_packages_provide_generic_framework_detection(self):
        self.write("package.json", '{"dependencies":{"@tauri-apps/api":"^2.11.1"}}')
        p = profile_repo(self.root)
        self.assertEqual(p.technologies["tauri"], "detected")
        self.assertIn("framework-tauri", p.slots)
        self.assertEqual(p.technologies["tauri-api"], "^2.11.1")

    def test_fingerprint_tracks_locks_and_runtime_but_ignores_generated_directories(self):
        from codex_bootstrap.profile import manifest_fingerprint

        self.write("package.json", "{}")
        self.write("pnpm-lock.yaml", "lockfileVersion: '9.0'")
        self.write(".nvmrc", "22")
        self.write(".codex/package.json", "{}")
        self.write(".cargo-target/package.json", "{}")
        self.write("index.ts", "secret implementation")
        before = manifest_fingerprint(self.root)
        self.assertEqual(set(before), {"package.json", "pnpm-lock.yaml", ".nvmrc"})
        self.assertEqual(before["package.json"], hashlib.sha256(b"{}").hexdigest())
        self.write("pnpm-lock.yaml", "lockfileVersion: '9.1'")
        self.assertNotEqual(before, manifest_fingerprint(self.root, profile_repo(self.root)))

    def test_large_locks_are_bounded_and_credential_specs_are_redacted(self):
        self.write("package-lock.json", " " * (16 * 1024 * 1024 + 1))
        self.write("package.json", '{"dependencies":{"lib":"https://user:secret@example.com/lib"}}')
        p = profile_repo(self.root)
        self.assertNotIn("package-lock.json", p.manifests)
        self.assertNotIn("secret", json.dumps(p.to_dict()))


if __name__ == "__main__":
    unittest.main()
