import base64
import json
import os
import subprocess
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from codex_bootstrap.discovery import REGISTRIES, discover
from codex_bootstrap.github import GitHub


class DiscoveryUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cache = Path(self.tmp.name) / "cache"

    def test_https_fallback_reuses_existing_gh_auth_without_caching_credentials(self):
        import io

        requests = []

        def response(request, **kwargs):
            requests.append(request)
            return io.BytesIO(b'{"private": false}')

        client = GitHub(cache_dir=self.cache)
        client.gh = "fixture-gh"
        with (
            patch.dict(os.environ, {"GH_TOKEN": "", "GITHUB_TOKEN": ""}),
            patch("codex_bootstrap.github.command", return_value="fixture-secret\n") as credentials,
            patch("codex_bootstrap.github.urllib.request.urlopen", side_effect=response),
        ):
            client._http("repos/example/public")
            client._http("repos/example/other")
        self.assertEqual(credentials.call_count, 1)
        self.assertEqual(
            credentials.call_args.args[0],
            ["fixture-gh", "auth", "token", "--hostname", "github.com"],
        )
        self.assertTrue(
            all(r.get_header("Authorization") == "Bearer fixture-secret" for r in requests)
        )
        self.assertFalse(self.cache.exists())

    def test_explicit_env_token_does_not_read_gh_credentials(self):
        import io

        client = GitHub(cache_dir=self.cache)
        client.gh = "fixture-gh"
        with (
            patch.dict(os.environ, {"GH_TOKEN": "env-fixture-secret"}),
            patch(
                "codex_bootstrap.github.command", side_effect=AssertionError("unexpected auth read")
            ),
            patch(
                "codex_bootstrap.github.urllib.request.urlopen", return_value=io.BytesIO(b"{}")
            ) as request,
        ):
            client._http("repos/example/public")
        self.assertEqual(
            request.call_args.args[0].get_header("Authorization"), "Bearer env-fixture-secret"
        )

    def test_public_snapshot_and_blob_cache_survives_new_client_and_expires(self):
        now, calls = [1000.0], []
        sha = "a" * 40

        def transport(endpoint):
            calls.append(endpoint)
            if endpoint == "repos/example/skills":
                return {"private": False, "default_branch": "main"}
            if "/commits/" in endpoint:
                return {"sha": sha}
            if "/trees/" in endpoint:
                return {"tree": [], "truncated": False}
            return {"size": 5, "encoding": "base64", "content": base64.b64encode(b"hello").decode()}

        first = GitHub(cache_dir=self.cache, transport=transport, clock=lambda: now[0])
        first.snapshot("example/skills")
        self.assertEqual(first.blob("example/skills", sha), b"hello")
        count = len(calls)
        second = GitHub(cache_dir=self.cache, transport=transport, clock=lambda: now[0])
        second.snapshot("example/skills")
        self.assertEqual(second.blob("example/skills", sha), b"hello")
        self.assertEqual(len(calls), count)
        self.assertGreaterEqual(second.stats["disk_cache_hits"], 4)
        now[0] += 10 * 86400
        third = GitHub(cache_dir=self.cache, transport=transport, clock=lambda: now[0])
        third.snapshot("example/skills")
        self.assertGreater(len(calls), count)

    def test_cache_excludes_private_repository_payloads_and_arbitrary_endpoints(self):
        client = GitHub(
            cache_dir=self.cache,
            transport=lambda endpoint: {"private": True, "secret": "private marker"},
        )
        client.api("repos/example/private")
        with self.assertRaises(ValueError):
            client.api("repos/example/private/actions/secrets")
        self.assertFalse(any("private marker" in p.read_text() for p in self.cache.glob("*.json")))

    def test_public_cache_omits_account_specific_authorization_metadata(self):
        client = GitHub(
            cache_dir=self.cache,
            transport=lambda endpoint: {
                "private": False,
                "default_branch": "main",
                "permissions": {"admin": True},
                "token": "never-persist-this",
            },
        )
        client.api("repos/example/public")
        cached = [json.loads(path.read_text())["value"] for path in self.cache.glob("*.json")]
        self.assertTrue(cached)
        self.assertNotIn("permissions", cached[0])
        self.assertNotIn("never-persist-this", json.dumps(cached))

    def test_transient_rate_limit_retry_is_bounded_and_reuses_search_cache(self):
        calls, sleeps = [], []

        def transport(endpoint):
            calls.append(endpoint)
            if len(calls) == 1:
                raise urllib.error.HTTPError(
                    "https://api.github.com", 429, "rate limit", {"Retry-After": "1"}, None
                )
            return {"items": [{"full_name": "public/skills", "private": False}]}

        client = GitHub(cache_dir=self.cache, transport=transport, sleep=sleeps.append)
        self.assertTrue(client.search("repos", "agent skills"))
        self.assertEqual(sleeps, [1.0])
        self.assertEqual(client.stats["retries"], 1)
        again = GitHub(cache_dir=self.cache, offline=True)
        self.assertTrue(again.search("repos", "agent skills"))
        self.assertFalse(again.errors)
        self.assertIn("is%3Apublic", calls[0])

    def test_long_rate_reset_stops_resource_without_sleep_or_repeated_requests(self):
        calls, sleeps = [], []

        def transport(endpoint):
            calls.append(endpoint)
            raise urllib.error.HTTPError(
                "https://api.github.com",
                403,
                "blocked",
                {"X-RateLimit-Remaining": "0", "Retry-After": "3600"},
                None,
            )

        client = GitHub(cache_dir=self.cache, transport=transport, sleep=sleeps.append)
        self.assertEqual(client.search("repos", "one"), [])
        self.assertEqual(client.search("repos", "two"), [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(sleeps, [])
        self.assertIn("rate limit", client.errors[0]["reason"].lower())

    def test_cache_is_bounded_and_corrupt_entries_are_ignored(self):
        client = GitHub(
            cache_dir=self.cache, cache_entries=2, transport=lambda endpoint: {"private": False}
        )
        for name in ("one", "two", "three"):
            client.api("repos/example/" + name)
        self.assertLessEqual(len(list(self.cache.glob("*.json"))), 2)
        for path in self.cache.glob("*.json"):
            path.write_text("not json")
        other = GitHub(
            cache_dir=self.cache, transport=lambda endpoint: {"private": False, "fresh": True}
        )
        self.assertTrue(other.api("repos/example/three")["fresh"])

    def test_cache_eviction_preserves_unrelated_json_in_shared_directory(self):
        self.cache.mkdir()
        foreign = {
            "settings.json": '{"important": "' + "x" * 4096 + '"}',
            "report.json": '{"result": "keep this report"}',
            "0" * 64 + ".json": json.dumps({"schema": 1, "fetched": 1, "value": {"user": "owned"}}),
        }
        for name, content in foreign.items():
            (self.cache / name).write_text(content)
        client = GitHub(
            cache_dir=self.cache,
            cache_entries=1,
            cache_bytes=512,
            transport=lambda endpoint: {"private": False},
        )
        for name in ("one", "two", "three"):
            client.api("repos/example/" + name)
        for name, content in foreign.items():
            self.assertTrue((self.cache / name).exists(), name)
            self.assertEqual((self.cache / name).read_text(), content)
        owned = [path for path in self.cache.glob("*.json") if path.name not in foreign]
        self.assertEqual(len(owned), 1)
        self.assertLessEqual(sum(path.stat().st_size for path in owned), 512)

    def test_cache_write_preserves_foreign_file_at_a_cache_key(self):
        client = GitHub(cache_dir=self.cache, transport=lambda endpoint: {"private": False})
        self.cache.mkdir()
        collision = client._cache_path("repos/example/public")
        collision.write_text('{"user": "keep this document"}')
        client.api("repos/example/public")
        self.assertEqual(collision.read_text(), '{"user": "keep this document"}')

    def test_timed_out_gh_cli_falls_back_to_https_within_shared_budget(self):
        client = GitHub(cache_dir=self.cache)
        client.gh = "fixture-gh"
        with (
            patch("codex_bootstrap.github.command", side_effect=subprocess.TimeoutExpired("gh", 1)),
            patch.object(client, "_http", return_value={"private": False}) as fallback,
        ):
            self.assertFalse(client.api("repos/example/public")["private"])
        fallback.assert_called_once()
        self.assertEqual(client.stats["requests"], 2)

    def test_gh_search_uses_both_explicit_cli_axes_and_persistent_cache(self):
        commands = []

        def command(args, **kwargs):
            commands.append((args, kwargs))
            if args[2] == "code":
                return json.dumps(
                    [
                        {
                            "repository": {"nameWithOwner": "example/public"},
                            "path": "unit-testing/SKILL.md",
                        }
                    ]
                )
            return json.dumps(
                [
                    {
                        "fullName": "example/public",
                        "stargazersCount": 23,
                        "updatedAt": "2026-10-01T00:00:00Z",
                    }
                ]
            )

        client = GitHub(cache_dir=self.cache)
        client.gh = "fixture-gh"
        with patch("codex_bootstrap.github.command", side_effect=command):
            code = client.search("code", 'filename:SKILL.md "testing"', limit=4)
            repos = client.search("repos", "agent skills", limit=3)
        self.assertEqual(code[0]["repository"]["nameWithOwner"], "example/public")
        self.assertEqual(repos[0]["fullName"], "example/public")
        self.assertEqual(commands[0][0][:3], ["fixture-gh", "search", "code"])
        self.assertEqual(commands[1][0][:3], ["fixture-gh", "search", "repos"])
        self.assertIn("is:public", commands[0][0][3])
        self.assertEqual(commands[0][0][commands[0][0].index("--limit") + 1], "4")
        self.assertEqual(commands[1][0][commands[1][0].index("--limit") + 1], "3")
        self.assertEqual(commands[0][0][commands[0][0].index("--json") + 1], "repository,path")
        self.assertEqual(
            commands[1][0][commands[1][0].index("--json") + 1], "fullName,stargazersCount,updatedAt"
        )
        self.assertEqual(commands[0][1]["env"]["GH_HOST"], "github.com")
        self.assertEqual(commands[1][1]["env"]["GH_HOST"], "github.com")
        cached = GitHub(cache_dir=self.cache, offline=True)
        self.assertEqual(cached.search("code", 'filename:SKILL.md "testing"', limit=4), code)
        self.assertEqual(cached.search("repos", "agent skills", limit=3), repos)
        self.assertEqual(cached.stats["requests"], 0)

    def test_failed_gh_search_falls_back_to_https_and_preserves_cache(self):
        client = GitHub(cache_dir=self.cache)
        client.gh = "fixture-gh"
        payload = {"items": [{"full_name": "example/public", "private": False}]}
        with (
            patch("codex_bootstrap.github.command", side_effect=RuntimeError("gh exited 1")),
            patch.object(client, "_http", return_value=payload) as fallback,
        ):
            self.assertEqual(client.search("repos", "agent skills"), payload["items"])
            self.assertEqual(client.search("repos", "agent skills"), payload["items"])
        fallback.assert_called_once()
        self.assertEqual(client.stats["requests"], 2)
        self.assertEqual(client.stats["memory_cache_hits"], 1)

    def test_structurally_invalid_cached_commit_is_refetched(self):
        sha = "a" * 40

        def transport(endpoint):
            return {"private": False} if endpoint == "repos/example/public" else {"sha": sha}

        first = GitHub(cache_dir=self.cache, transport=transport)
        first.api("repos/example/public")
        first.api("repos/example/public/commits/main")
        commit_cache = first._cache_path("repos/example/public/commits/main")
        record = json.loads(commit_cache.read_text())
        record["value"] = {"not-a-commit": True}
        commit_cache.write_text(json.dumps(record))
        second = GitHub(cache_dir=self.cache, transport=transport)
        second.api("repos/example/public")
        self.assertEqual(second.api("repos/example/public/commits/main")["sha"], sha)

    def test_registry_work_is_interleaved_and_subset_queries_use_scoped_technology(self):
        events = []

        class Fixture:
            queries, errors = [], []

            def search(self, kind, query, limit=4):
                self.queries.append({"kind": kind, "query": query})
                return []

            def snapshot(self, repository):
                events.append(("snapshot", repository))
                return (
                    {"license": {"spdx_id": "MIT"}},
                    "a" * 40,
                    [
                        {
                            "path": f"skills/vitest-{i}/SKILL.md",
                            "type": "blob",
                            "mode": "100644",
                            "sha": str(i),
                            "size": 300,
                        }
                        for i in range(4)
                    ],
                )

            def blob(self, repository, sha, max_size=256000):
                events.append(("blob", repository))
                return b"---\nname: vitest\ndescription: Unit testing with Vitest.\n---\nTest public behavior with deterministic fixtures. Verify edge cases and failures using Vitest.\n"

        profile = SimpleNamespace(
            slots=["unit-testing", "framework-react"],
            technologies={"vitest": "3", "react": "19"},
            slot_technologies={"unit-testing": ["vitest"], "framework-react": ["react"]},
        )
        fixture = Fixture()
        candidates, report = discover(profile, fixture, slots=["unit-testing"])
        self.assertTrue(candidates)
        first_blobs = [repo for operation, repo in events if operation == "blob"][:4]
        self.assertEqual(set(first_blobs), set(REGISTRIES))
        queries = [q["query"] for q in report["queries"]]
        self.assertTrue(any("unit testing" in query.lower() for query in queries))
        self.assertFalse(any("react" in query.lower() for query in queries))
        self.assertTrue(all(c.slot == "unit-testing" for c in candidates))
        self.assertIn("degraded", report)

    def test_generic_queries_keep_semantics_with_a_large_dependency_profile(self):
        from codex_bootstrap.discovery import terms_for

        profile = SimpleNamespace(
            slots=["architecture", "framework-tauri"],
            technologies={f"dependency-{i}": "1" for i in range(72)},
            slot_technologies={
                "architecture": ["@eslint/js", *[f"dependency-{i}" for i in range(72)]],
                "framework-tauri": ["tauri", *[f"dependency-{i}" for i in range(72)]],
            },
        )
        self.assertEqual(terms_for("architecture", profile), ["architecture", "module design"])
        self.assertEqual(terms_for("framework-tauri", profile)[0], "tauri")
        self.assertLessEqual(len(terms_for("framework-tauri", profile)), 8)

        class Fixture:
            queries, errors = [], []

            def search(self, kind, query, limit=4):
                self.queries.append({"kind": kind, "query": query})
                return []

            def snapshot(self, repository):
                return {}, "a" * 40, []

        _, report = discover(profile, Fixture())
        code_queries = [query["query"] for query in report["queries"] if query["kind"] == "code"]
        self.assertIn('filename:SKILL.md "architecture"', code_queries)
        self.assertFalse(any("eslint" in query or "dependency-" in query for query in code_queries))

    def test_large_registry_matching_prepares_literals_once_without_regex_churn(self):
        import codex_bootstrap.discovery as discovery

        class Fixture:
            queries, errors = [], []

            def search(self, kind, query, limit=4):
                self.queries.append({"kind": kind, "query": query})
                return []

            def snapshot(self, repository):
                return (
                    {},
                    "a" * 40,
                    [
                        {
                            "path": f"unmatched-{i}/SKILL.md",
                            "type": "blob",
                            "mode": "100644",
                            "sha": "b" * 40,
                            "size": 200,
                        }
                        for i in range(12_000)
                    ],
                )

        dependencies = [f"dependency-{i}" for i in range(72)]
        slots = [
            "architecture",
            "security",
            "performance",
            "documentation",
            *[f"framework-example{i}" for i in range(29)],
        ]
        profile = SimpleNamespace(
            slots=slots,
            technologies=dict.fromkeys(dependencies, "1"),
            slot_technologies=dict.fromkeys(slots, dependencies),
        )
        started = time.monotonic()
        with (
            patch.object(discovery, "terms_for", wraps=discovery.terms_for) as terms,
            patch.object(discovery.re, "search", wraps=discovery.re.search) as regex,
        ):
            candidates, report = discover(profile, Fixture())
        self.assertEqual(candidates, [])
        self.assertLess(terms.call_count, 400)
        self.assertLess(regex.call_count, 1000)
        self.assertLess(time.monotonic() - started, 8)
        self.assertTrue(report["degraded"])
        self.assertTrue(any("index" in item["reason"] for item in report["rejected"]))

    def test_registry_network_quota_does_not_starve_other_registries(self):
        from collections import Counter

        counts = Counter()
        sha = "a" * 40
        skill = b"---\nname: unit-testing\ndescription: Unit testing of changed behavior.\n---\nUse deterministic fixtures to test public outcomes. Verify boundary cases and failures.\n"

        def transport(endpoint):
            if endpoint.startswith("search/"):
                return {"items": []}
            repository = "/".join(endpoint.split("/")[1:3])
            counts[repository] += 1
            if endpoint == "repos/" + repository:
                return {"private": False, "license": {"spdx_id": "MIT"}}
            if "/commits/" in endpoint:
                return {"sha": sha}
            if "/trees/" in endpoint:
                resources = [
                    {
                        "path": f"skills/unit-testing/references/{i}.md",
                        "type": "blob",
                        "mode": "100644",
                        "sha": f"{i + 1:040x}",
                        "size": 10,
                    }
                    for i in range(40 if repository == REGISTRIES[0] else 0)
                ]
                return {
                    "tree": [
                        {
                            "path": "skills/unit-testing/SKILL.md",
                            "type": "blob",
                            "mode": "100644",
                            "sha": "b" * 40,
                            "size": len(skill),
                        },
                        *resources,
                    ]
                }
            content = skill if endpoint.endswith("b" * 40) else b"reference"
            return {
                "size": len(content),
                "encoding": "base64",
                "content": base64.b64encode(content).decode(),
            }

        client = GitHub(cache_dir=self.cache, transport=transport)
        profile = SimpleNamespace(slots=["unit-testing"], technologies={}, slot_technologies={})
        candidates, report = discover(profile, client)
        self.assertLessEqual(counts[REGISTRIES[0]], 28)
        self.assertEqual({c.repository for c in candidates}, set(REGISTRIES[1:]))
        self.assertTrue(report["degraded"])
        self.assertTrue(all(counts[r] >= 4 for r in REGISTRIES))

    def test_many_search_hits_leave_budget_for_candidates_from_multiple_repositories(self):
        supplemental = [f"example/skills-{index:02}" for index in range(12)]
        blob_repositories = set()
        skill = b"---\nname: unit-testing\ndescription: Unit testing changed behavior.\n---\nUse deterministic fixtures. Test public outcomes. Check edge cases and failure cases.\n"

        def transport(endpoint):
            if endpoint.startswith("search/"):
                return {
                    "items": [
                        {"full_name": repository, "private": False} for repository in supplemental
                    ]
                }
            repository = "/".join(endpoint.split("/")[1:3])
            if endpoint == "repos/" + repository:
                return {"private": False, "license": {"spdx_id": "MIT"}}
            if "/commits/" in endpoint:
                return {"sha": "a" * 40}
            if "/trees/" in endpoint:
                return {
                    "tree": []
                    if repository in REGISTRIES
                    else [
                        {
                            "path": "unit-testing/SKILL.md",
                            "type": "blob",
                            "mode": "100644",
                            "sha": "b" * 40,
                            "size": len(skill),
                        }
                    ]
                }
            blob_repositories.add(repository)
            return {
                "encoding": "base64",
                "content": base64.b64encode(skill).decode(),
                "size": len(skill),
            }

        client = GitHub(cache_dir=self.cache, transport=transport)
        profile = SimpleNamespace(slots=["unit-testing"], technologies={}, slot_technologies={})
        candidates, report = discover(profile, client)
        self.assertGreaterEqual(len(blob_repositories), 2)
        self.assertGreaterEqual(len({candidate.repository for candidate in candidates}), 2)
        self.assertLessEqual(client.stats["requests"], 180)
        self.assertTrue(all(candidate.repository in supplemental for candidate in candidates))
        self.assertFalse(report["degraded"])

    def test_ineligible_skill_is_rejected_before_resources_are_downloaded(self):
        from codex_bootstrap.discovery import candidate_from_tree
        from codex_bootstrap.profile import Profile

        calls = []

        class Fixture:
            def blob(self, repository, sha, max_size=256000):
                calls.append(sha)
                return b"---\nname: unit-testing\ndescription: Unit testing of changed behavior.\nrequired-tools: [missing-connector]\n---\nUse deterministic fixtures. Test public behavior and verify failure cases.\n"

        tree = [
            {
                "path": "unit-testing/SKILL.md",
                "type": "blob",
                "mode": "100644",
                "sha": "skill",
                "size": 200,
            },
            {
                "path": "unit-testing/expensive.md",
                "type": "blob",
                "mode": "100644",
                "sha": "resource",
                "size": 200,
            },
        ]
        with self.assertRaisesRegex(ValueError, "missing required tool"):
            candidate_from_tree(
                Fixture(),
                "example/skills",
                {},
                "a" * 40,
                tree,
                "unit-testing/SKILL.md",
                ["unit-testing"],
                Profile(),
            )
        self.assertEqual(calls, ["skill"])

    def test_empty_refresh_subset_performs_no_work(self):
        profile = SimpleNamespace(slots=["unit-testing"])
        client = GitHub(cache_dir=self.cache, offline=True)
        candidates, report = discover(profile, client, slots=[])
        self.assertEqual(candidates, [])
        self.assertEqual(report["queries"], [])
        self.assertFalse(report["degraded"])

    def test_rtk_latest_release_route_preserves_install_fields_and_public_cache_policy(self):
        release = {
            "tag_name": "v1.2.3",
            "assets": [
                {
                    "name": "rtk-x86_64-pc-windows-msvc.zip",
                    "digest": "sha256:" + "a" * 64,
                    "browser_download_url": "https://github.com/rtk-ai/rtk/releases/download/v1.2.3/rtk.zip",
                    "uploader": {"account-specific": True},
                }
            ],
            "author": {"account-specific": True},
        }

        def transport(endpoint):
            return {"private": False} if endpoint == "repos/rtk-ai/rtk" else release

        client = GitHub(cache_dir=self.cache, transport=transport)
        self.assertEqual(client.api("repos/rtk-ai/rtk/releases/latest"), release)
        self.assertEqual(list(self.cache.glob("*.json")), [])
        public = GitHub(cache_dir=self.cache, transport=transport)
        public.api("repos/rtk-ai/rtk")
        public.api("repos/rtk-ai/rtk/releases/latest")
        offline = GitHub(cache_dir=self.cache, offline=True)
        offline.api("repos/rtk-ai/rtk")
        cached = offline.api("repos/rtk-ai/rtk/releases/latest")
        self.assertEqual(cached["tag_name"], "v1.2.3")
        self.assertEqual(cached["assets"][0]["name"], release["assets"][0]["name"])
        self.assertEqual(cached["assets"][0]["digest"], release["assets"][0]["digest"])
        self.assertEqual(
            cached["assets"][0]["browser_download_url"],
            release["assets"][0]["browser_download_url"],
        )
        self.assertNotIn("uploader", cached["assets"][0])
        self.assertNotIn("author", cached)


if __name__ == "__main__":
    unittest.main()
