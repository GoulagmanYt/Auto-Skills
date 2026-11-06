import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_bootstrap.profile import Profile
from codex_bootstrap.proposal import selection_plan
from codex_bootstrap.selection import Candidate


def guide(name="local-rust", slot="language-rust"):
    return (
        f"---\nname: {name}\ndescription: Check Rust ownership and error handling.\n"
        f"x-bootstrap-slot: {slot}\n---\n"
        "Read the Rust implementation. Check ownership and lifetimes, verify error handling, "
        "and run focused regression tests before documenting the result.\n"
    )


class AutomaticInventoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        # macOS temporary directories can use the system /var -> /private/var
        # alias. Test admissible bundles under their canonical fixture root;
        # linked bundle paths remain deliberately ineligible for copying.
        self.directory = Path(temporary.name).resolve()
        self.cache = self.directory / "cache"
        self.profile = Profile(technologies={"rust": "detected"}, slots=["language-rust"])
        self.path = self.directory / "user-skills/rust/SKILL.md"
        self.path.parent.mkdir(parents=True)
        self.path.write_text(guide(), encoding="utf-8")

    def test_admissible_local_skill_prevents_equivalent_remote_search(self):
        with patch("codex_bootstrap.proposal.discover") as network:
            selected, report = selection_plan(
                self.profile, local_paths=[self.path], cache_dir=self.cache
            )
        self.assertEqual(selected[0].source, "local")
        self.assertEqual(selected[0].body, guide())
        self.assertEqual(selected[0].origin_path, str(self.path.resolve()))
        network.assert_not_called()
        self.assertEqual(report["coverage"]["local_slots"], ["language-rust"])

    def test_only_missing_local_capabilities_are_searched(self):
        self.profile.slots.append("unit-testing")
        with patch("codex_bootstrap.proposal.discover", return_value=([], {})) as network:
            selected, _ = selection_plan(
                self.profile, local_paths=[self.path], cache_dir=self.cache
            )
        self.assertEqual(network.call_args.kwargs["slots"], {"unit-testing"})
        self.assertEqual(selected[0].source, "local")

    def test_invalid_local_dependencies_fall_back_without_executing(self):
        self.path.write_text(guide() + "Read [missing](references/missing.md).\n")
        selected, report = selection_plan(
            self.profile, offline=True, local_paths=[self.path], cache_dir=self.cache
        )
        self.assertEqual(selected[0].source, "bundled")
        self.assertTrue(report["inventory"]["rejected"])

    def test_pinned_remote_bundle_is_reused_offline_across_repositories(self):
        remote = Candidate(
            slot="language-rust",
            name="remote-rust",
            body=guide("remote-rust"),
            repository="openai/skills",
            commit="a" * 40,
            remote_path="skills/rust/SKILL.md",
            license="MIT",
        )
        with patch("codex_bootstrap.proposal.discover", return_value=([remote], {})):
            first, _ = selection_plan(self.profile, local_paths=[], cache_dir=self.cache)
        second, report = selection_plan(
            self.profile, offline=True, local_paths=[], cache_dir=self.cache
        )
        self.assertEqual(first[0].source, "github")
        self.assertEqual(second[0].commit, "a" * 40)
        self.assertEqual(second[0].body, remote.body)
        self.assertEqual(report["inventory"]["shared_hits"], 1)
        bundle = next((self.cache / "bundles-v1").glob("*.json"))
        value = json.loads(bundle.read_text())
        value["candidate"]["body"] += "tampered"
        bundle.write_text(json.dumps(value))
        third, report = selection_plan(
            self.profile, offline=True, local_paths=[], cache_dir=self.cache
        )
        self.assertEqual(third[0].source, "bundled")
        self.assertTrue(report["inventory"]["rejected"])

    def test_preexisting_repo_skill_survives_bootstrap_and_uninstall(self):
        from codex_bootstrap.bootstrap import bootstrap
        from codex_bootstrap.repository_uninstall import uninstall_repository

        root = self.directory / "repo"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / "Cargo.toml").write_text('[package]\nname="example"\nversion="0.1.0"\n')
        existing = root / ".agents/skills/user-rust/SKILL.md"
        existing.parent.mkdir(parents=True)
        existing.write_text(guide())
        before = existing.read_bytes()
        bootstrap(root, offline=True, cache_dir=self.cache)
        self.assertEqual(uninstall_repository(root)["status"], "uninstalled")
        self.assertEqual(existing.read_bytes(), before)

    def test_discovery_does_not_download_from_unapproved_sources(self):
        from codex_bootstrap.discovery import discover

        class Source:
            queries, errors = [], []

            def search(self, kind, query, limit=4):
                return [{"full_name": "unknown/agent-skills"}]

            def snapshot(self, repository):
                self.repositories.append(repository)
                return {"license": {"spdx_id": "MIT"}}, "a" * 40, []

        source = Source()
        source.repositories = []
        discover(self.profile, source, allowed_repositories={"openai/skills"})
        self.assertEqual(source.repositories, ["openai/skills"])

    def test_failed_gh_transport_is_not_retried_for_every_blob(self):
        from codex_bootstrap.github import GitHub

        client = GitHub(cache_dir=self.cache)
        client.gh = "fixture-gh"
        with (
            patch(
                "codex_bootstrap.github.command", side_effect=RuntimeError("gh unavailable")
            ) as gh,
            patch.object(client, "_http", return_value={"private": False}),
        ):
            client.api("repos/example/one")
            client.api("repos/example/two")
        self.assertEqual(gh.call_count, 1)
        self.assertEqual(client.stats["requests"], 3)

    def test_pinned_skill_license_declaration_is_recognized(self):
        from codex_bootstrap.discovery import candidate_from_tree

        body = guide().replace("x-bootstrap-slot:", "license: MIT\nx-bootstrap-slot:")

        class Source:
            def blob(self, repository, sha, max_size=256000):
                return body.encode()

        path = "skills/rust/SKILL.md"
        candidate = candidate_from_tree(
            Source(),
            "openai/skills",
            {},
            "a" * 40,
            [{"path": path, "mode": "100644", "type": "blob", "sha": "b" * 40, "size": len(body)}],
            path,
            ["language-rust"],
            self.profile,
        )
        self.assertEqual(candidate.license, "MIT")
        self.assertEqual(candidate.license_origin, "skill-frontmatter")

    def test_existing_same_slot_in_both_native_locations_is_reused_and_preserved(self):
        from codex_bootstrap.bootstrap import bootstrap, verify_lock
        from codex_bootstrap.repository_uninstall import uninstall_repository

        root = self.directory / "collision"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / "Cargo.toml").write_text('[package]\nname="example"\nversion="0.1.0"')
        originals = []
        for folder in (".agents/skills", ".codex/skills"):
            path = root / folder / "language-rust/SKILL.md"
            path.parent.mkdir(parents=True)
            path.write_text(guide())
            originals.append(path)
        lock = bootstrap(root, offline=True, cache_dir=self.cache)
        rust = next(s for s in lock["skills"] if s["slot"] == "language-rust")
        self.assertEqual(rust["source"], "local")
        self.assertNotEqual(root / rust["path"], originals[1])
        self.assertEqual(verify_lock(root), lock)
        self.assertEqual(uninstall_repository(root)["status"], "uninstalled")
        self.assertTrue(all(p.read_text() == guide() for p in originals))

    def test_optional_shared_cache_failure_does_not_abort_valid_selection(self):
        remote = Candidate(
            slot="language-rust",
            name="remote-rust",
            body=guide("remote-rust"),
            repository="openai/skills",
            commit="a" * 40,
            license="MIT",
        )
        with (
            patch("codex_bootstrap.proposal.discover", return_value=([remote], {})),
            patch(
                "codex_bootstrap.inventory.atomic_write", side_effect=PermissionError("cache busy")
            ),
        ):
            selected, report = selection_plan(self.profile, local_paths=[], cache_dir=self.cache)
        self.assertEqual(selected[0].source, "github")
        self.assertEqual(report["inventory"]["cache_errors"], 1)

    def test_concurrent_bundle_eviction_keeps_valid_cache_entries(self):
        from concurrent.futures import ThreadPoolExecutor
        from dataclasses import replace

        from codex_bootstrap.inventory import store_bundle

        base = Candidate(
            slot="language-rust",
            name="remote-rust",
            body=guide("remote-rust"),
            repository="openai/skills",
            commit="a" * 40,
            license="MIT",
        )
        for number in range(256):
            self.assertTrue(store_bundle(replace(base, name=f"cached-{number}"), self.cache))
        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(
                executor.map(
                    lambda number: store_bundle(replace(base, name=f"new-{number}"), self.cache),
                    range(64),
                )
            )
        self.assertEqual(len(results), 64)
        for path in (self.cache / "bundles-v1").glob("*.json"):
            value = json.loads(path.read_text())
            self.assertEqual(value["sha256"], path.stem)

    def test_missing_specialty_gets_targeted_search_before_common_roles(self):
        from codex_bootstrap.profile import BASE_SLOTS

        profile = Profile(technologies={"rust": "detected"}, slots=[*BASE_SLOTS, "language-rust"])
        remote = Candidate(
            slot="language-rust",
            name="remote-rust",
            body=guide("remote-rust"),
            repository="openai/skills",
            commit="a" * 40,
            license="MIT",
        )
        calls = []

        def discover(profile, github=None, *, slots, **kwargs):
            calls.append((set(slots), github))
            return ([remote] if set(slots) == {"language-rust"} else []), {}

        with patch("codex_bootstrap.proposal.discover", side_effect=discover):
            selected, _ = selection_plan(profile, local_paths=[], cache_dir=self.cache)
        self.assertEqual(next(c for c in selected if c.slot == "language-rust").source, "github")
        self.assertEqual(calls[0][0], {"language-rust"})
        self.assertIsNotNone(calls[0][1])
        self.assertTrue(all(client is calls[0][1] for _, client in calls))


if __name__ == "__main__":
    unittest.main()
