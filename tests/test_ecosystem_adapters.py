import json
import os
import tempfile
import unittest
from pathlib import Path

from codex_bootstrap.catalog import bundled_candidates
from codex_bootstrap.profile import MANIFEST_LIMIT, manifest_fingerprint, profile_repo
from codex_bootstrap.proposal import propose
from codex_bootstrap.selection import Candidate, select
from codex_bootstrap.workspaces import workspace_profiles


class EcosystemAdapterTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_cmake_cpp_service_is_independent_of_react_frontend(self):
        self.write("package.json", json.dumps({"dependencies": {"react": "^19"}}))
        self.write(
            "engine/CMakeLists.txt",
            "cmake_minimum_required(VERSION 3.24)\nproject(engine VERSION 8.9 LANGUAGES CXX)\nset(CMAKE_CXX_STANDARD 20)\n",
        )
        profiles = workspace_profiles(self.root)
        self.assertEqual(set(profiles), {".", "engine"})
        self.assertNotIn("cpp", profiles["."].technologies)
        native = profiles["engine"]
        self.assertEqual(native.technologies["cpp"], "20")
        self.assertEqual(native.technologies["cmake"], ">=3.24")
        self.assertNotIn("react", native.technologies)
        self.assertIn("build-cmake", {c.slot for c in bundled_candidates(native)})

    def test_static_manifest_ecosystems_have_guides_without_project_version_leaks(self):
        fixtures = [
            (
                "meson.build",
                "project('engine', 'cpp', version: '9.8', meson_version: '>=1.2', default_options: ['cpp_std=c++17'])",
                {"cpp": "17", "meson": ">=1.2"},
                "build-meson",
            ),
            (
                "pubspec.yaml",
                "name: app\nversion: 9.8.0\nenvironment:\n  sdk: '>=3.4.0 <4.0.0'\ndependencies:\n  flutter:\n    sdk: flutter\n  http: ^1.2.0\n",
                {"dart": ">=3.4.0 <4.0.0", "flutter": "detected", "http": "^1.2.0"},
                "framework-flutter",
            ),
            (
                "Package.swift",
                '// swift-tools-version: 5.9\nimport PackageDescription\nlet package = Package(name: "App", swiftLanguageVersions: [.v5])',
                {"swift": "5", "swift-tools": "5.9"},
                "language-swift",
            ),
            (
                "mix.exs",
                'def project do\n [app: :demo, version: "9.8", elixir: "~> 1.16", deps: [{:phoenix, "~> 1.7"}]]\nend',
                {"elixir": "~> 1.16", "phoenix": "~> 1.7"},
                "framework-phoenix",
            ),
            (
                "DESCRIPTION",
                "Package: example\nVersion: 9.8.0\nDepends: R (>= 4.3), methods\nImports: ggplot2 (>= 3.5),\n    dplyr\n",
                {"r": ">= 4.3", "ggplot2": ">= 3.5"},
                "language-r",
            ),
            (
                "Project.toml",
                'name = "Research"\nversion = "9.8.0"\n[deps]\nDataFrames = "a93c6f00-e57d-5684-b7b6-d8193f3e46c0"\n[compat]\njulia = "1.10"\nDataFrames = "1.6"\n',
                {"julia": "1.10", "dataframes": "1.6"},
                "language-julia",
            ),
        ]
        for index, (name, text, expected, slot) in enumerate(fixtures):
            with self.subTest(name=name):
                folder = self.root / str(index)
                self.write(f"{index}/{name}", text)
                profile = profile_repo(folder)
                for technology, version in expected.items():
                    self.assertEqual(profile.technologies.get(technology), version)
                self.assertIn(slot, {c.slot for c in bundled_candidates(profile)})
                self.assertNotIn("9.8.0", profile.technologies.values())

    def test_swift_tools_header_does_not_invent_a_swift_language_version(self):
        self.write(
            "Package.swift",
            '// swift-tools-version: 6.0\nimport PackageDescription\nlet package = Package(name: "Demo")',
        )
        profile = profile_repo(self.root)
        self.assertEqual(profile.technologies.get("swift"), "detected")
        self.assertEqual(profile.technologies.get("swift-tools"), "6.0")

    def test_renv_records_r_runtime_and_package_lock_evidence(self):
        self.write(
            "renv.lock",
            json.dumps(
                {
                    "R": {"Version": "4.4.1"},
                    "Packages": {"ggplot2": {"Package": "ggplot2", "Version": "3.5.1"}},
                }
            ),
        )
        profile = profile_repo(self.root)
        self.assertEqual(profile.technologies.get("r"), "4.4.1")
        self.assertNotIn("ggplot2", profile.technologies)
        self.assertEqual(profile.resolved_versions["ggplot2"], ["3.5.1"])

    def test_scan_reports_bounded_exclusions_and_never_merges_submodules(self):
        self.write("vendor-engine/.git", "gitdir: ../.git/modules/vendor-engine")
        self.write("vendor-engine/CMakeLists.txt", "project(ignored LANGUAGES CXX)")
        self.write("large/pubspec.yaml", "x" * (MANIFEST_LIMIT + 1))
        self.write("a/b/c/d/e/f/g/h/i/Project.toml", '[compat]\njulia = "1.10"')
        profile = profile_repo(self.root)
        self.assertNotIn("cpp", profile.technologies)
        codes = {item["code"] for item in profile.diagnostics}
        self.assertTrue(
            {"submodule-boundary", "manifest-too-large", "scan-depth-limit"}.issubset(codes)
        )
        self.assertNotIn("vendor-engine", workspace_profiles(self.root))

    def test_conan_text_dependencies_do_not_set_cpp_language_version(self):
        self.write("conanfile.txt", "[requires]\nfmt/10.2.1\n[generators]\nCMakeDeps\n")
        profile = profile_repo(self.root)
        self.assertEqual(profile.technologies.get("cpp"), "detected")
        self.assertEqual(profile.technologies.get("fmt"), "10.2.1")
        self.assertIn("build-conan", profile.slots)

    def test_offline_proposal_covers_each_new_workspace_without_installing(self):
        self.write("web/package.json", '{"dependencies":{"react":"^19"}}')
        self.write(
            "engine/CMakeLists.txt", "project(engine LANGUAGES CXX)\nset(CMAKE_CXX_STANDARD 23)"
        )
        self.write("research/Project.toml", '[compat]\njulia = "1.10"')
        report = propose(self.root, offline=True)
        chosen = {(item["scope"], item["slot"]) for item in report["selected"]}
        self.assertTrue(
            {
                ("engine", "language-cpp"),
                ("engine", "build-cmake"),
                ("research", "language-julia"),
                ("web", "framework-react"),
            }.issubset(chosen)
        )
        self.assertEqual(report["coverage"]["uncovered"], [])
        self.assertFalse((self.root / ".agents").exists())

    def test_parse_errors_are_structured_and_do_not_hide_other_workspaces(self):
        self.write("bad/Project.toml", "[deps\n")
        self.write("good/Package.swift", "// swift-tools-version: 6.0\nimport PackageDescription")
        profile = profile_repo(self.root)
        self.assertEqual(profile.technologies.get("swift-tools"), "6.0")
        self.assertIn(
            {
                "code": "manifest-parse-error",
                "path": "bad/Project.toml",
                "message": "TOMLDecodeError",
            },
            profile.diagnostics,
        )

    def test_build_comments_and_computed_requirements_do_not_create_versions(self):
        self.write(
            "CMakeLists.txt",
            "#[[project(fake LANGUAGES C)\nset(CMAKE_CXX_STANDARD 99)]]\nproject(real VERSION 9.8 LANGUAGES CXX)\nset(CMAKE_CXX_STANDARD ${SELECTED_STANDARD})",
        )
        self.write(
            "mix.exs",
            '# elixir: "~> 9.8"\ndef project, do: [elixir: System.get_env("ELIXIR_REQUIREMENT")]',
        )
        profile = profile_repo(self.root)
        self.assertEqual(profile.technologies.get("cpp"), "detected")
        self.assertEqual(profile.technologies.get("elixir"), "detected")
        self.assertNotIn("c", profile.technologies)

    def test_relative_repository_paths_keep_manifest_provenance_and_fingerprints(self):
        self.write("Project.toml", '[compat]\njulia = "1.10"')
        relative = Path(os.path.relpath(self.root))
        self.assertEqual(profile_repo(relative).technologies.get("julia"), "1.10")
        self.assertEqual(set(manifest_fingerprint(relative)), {"Project.toml"})

    def test_malformed_conan_manifest_does_not_abort_other_profiles(self):
        self.write("native/conanfile.txt", "not a valid section\n")
        self.write("mobile/pubspec.yaml", "environment:\n  sdk: '^3.4.0'\n")
        profile = profile_repo(self.root)
        self.assertEqual(profile.technologies.get("dart"), "^3.4.0")
        self.assertTrue(
            any(
                item["code"] == "manifest-parse-error" and item["path"] == "native/conanfile.txt"
                for item in profile.diagnostics
            )
        )

    def test_pubspec_keeps_explicit_flutter_and_dart_constraints_separate(self):
        self.write(
            "pubspec.yaml",
            "environment:\n  sdk: '>=3.4.0 <4.0.0'\n  flutter: '>=3.22.0'\ndependencies:\n  flutter:\n    sdk: flutter\n",
        )
        profile = profile_repo(self.root)
        self.assertEqual(profile.technologies.get("dart"), ">=3.4.0 <4.0.0")
        self.assertEqual(profile.technologies.get("flutter"), ">=3.22.0")

    def test_julia_default_caret_and_union_do_not_certify_narrow_guides(self):
        for spec, normalized in (("1.10", "^1.10"), ("1.10, 2", "^1.10 || ^2")):
            with self.subTest(spec=spec):
                self.write("Project.toml", f'[compat]\njulia = "{spec}"')
                profile = profile_repo(self.root)
                source = profile.technology_sources["julia"][0]
                self.assertEqual(source["version"], spec)
                self.assertEqual(source.get("constraint"), normalized)
                candidate = Candidate(
                    slot="language-julia",
                    name="narrow-julia",
                    body="---\nname: narrow-julia\ndescription: Check Julia numerical package changes.\n---\n"
                    + "Follow existing Julia package checks and preserve numerical types and numerical precision. "
                    * 4,
                    compatibility={"julia": ">=1.10 <1.11"},
                )
                chosen, rejected = select([candidate], profile)
                self.assertEqual(chosen, [])
                self.assertTrue(any("incompatible" in item["reason"] for item in rejected))

    def test_julia_dependency_compat_uses_julia_semantics(self):
        self.write("Project.toml", '[deps]\nExample = "uuid"\n[compat]\nExample = "0.2, 1"')
        profile = profile_repo(self.root)
        self.assertEqual(profile.technology_sources["example"][0]["constraint"], "^0.2 || ^1")

    def test_cmake_computed_numeric_prefix_is_not_language_version_evidence(self):
        for value in ("2${CPP_DIGIT}", '"2${CPP_DIGIT}"', "20_suffix", '"20"tail'):
            with self.subTest(value=value):
                self.write(
                    "CMakeLists.txt",
                    f"project(engine LANGUAGES CXX)\nset(CMAKE_CXX_STANDARD {value})",
                )
                profile = profile_repo(self.root)
                self.assertEqual(profile.technologies.get("cpp"), "detected")
                self.assertTrue(
                    all(
                        source["version"] == "detected"
                        for source in profile.technology_sources["cpp"]
                    )
                )
                candidate = Candidate(
                    slot="language-cpp",
                    name="narrow-cpp",
                    body="---\nname: narrow-cpp\ndescription: Check C++ native package changes.\n---\n"
                    + "Follow existing C++ package checks and preserve ownership and lifetime constraints. "
                    * 4,
                    compatibility={"cpp": ">=2 <3"},
                )
                chosen, rejected = select([candidate], profile)
                self.assertEqual(chosen, [])
                self.assertTrue(any("incompatible" in item["reason"] for item in rejected))

    def test_cmake_command_text_in_messages_and_brackets_is_not_a_declaration(self):
        self.write(
            "CMakeLists.txt",
            'message("project(fake LANGUAGES CXX) set(CMAKE_CXX_STANDARD 20)")\nmessage([=[set(CMAKE_CXX_STANDARD 23)]=])',
        )
        profile = profile_repo(self.root)
        self.assertNotIn("cpp", profile.technologies)


if __name__ == "__main__":
    unittest.main()
