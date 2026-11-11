import io
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from suite_support import IsolatedTestCase


class AgentSelectionTests(IsolatedTestCase):
    def test_referenced_resources_can_be_fully_paged_before_choice(self):
        import os

        from test_automatic_inventory import guide

        from codex_bootstrap.agent_selection import candidates, inspect_candidate

        folder = Path(os.environ["CODEX_HOME"]) / "skills/local-rust"
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(guide())
        for index in range(10):
            (folder / f"{index:02}.md").write_text("Safe reference text. " * 900)
        catalog = candidates(self.root, ".", "language-rust", offline=True)
        local = next(c for c in catalog["candidates"] if c["source"] == "local")
        a = inspect_candidate(self.root, catalog["catalog_id"], local["id"], resource="09.md")
        b = inspect_candidate(
            self.root, catalog["catalog_id"], local["id"], resource="09.md", offset=a["next_offset"]
        )
        self.assertEqual(a["text"] + b["text"], (folder / "09.md").read_text())

    def test_seed_return_ignores_a_deferred_optional_tool(self):
        import os

        from codex_bootstrap.bootstrap import bootstrap

        (self.root / "package.json").write_text('{"dependencies":{"react":"^19"}}')
        bootstrap(self.root, seed_only=True)
        config = Path(os.environ["CODEX_HOME"]) / "auto-skills.toml"
        config.parent.mkdir(parents=True, exist_ok=True)
        config.write_text('[automatic]\noptional_tools=["repomix"]\n')
        # Repomix was deferred before global authorization. A fast launch must
        # not refresh forever while deliberately deferring installation work.
        path = self.root / ".codex/skills-lock.json"
        before = path.read_bytes()
        bootstrap(self.root, seed_only=True)
        self.assertEqual(path.read_bytes(), before)

    def test_offline_catalog_exposes_all_cached_alternatives(self):
        from test_automatic_inventory import guide

        from codex_bootstrap.agent_selection import candidates
        from codex_bootstrap.bootstrap import bootstrap
        from codex_bootstrap.inventory import store_bundle
        from codex_bootstrap.selection import Candidate

        bootstrap(self.root, seed_only=True)
        for name in ("cached-rust-a", "cached-rust-b"):
            store_bundle(
                Candidate(
                    slot="language-rust",
                    name=name,
                    body=guide(name),
                    repository="openai/skills",
                    commit="a" * 40,
                    license="MIT",
                )
            )
        result = candidates(self.root, ".", "language-rust", offline=True)
        self.assertTrue(
            {"cached-rust-a", "cached-rust-b"}.issubset({c["name"] for c in result["candidates"]})
        )

    def test_progress_has_a_heartbeat_while_an_operation_blocks(self):
        import threading

        from codex_bootstrap.progress import Progress

        heartbeat = threading.Event()

        class Stream(io.StringIO):
            def write(self, value):
                if "still working" in value:
                    heartbeat.set()
                return super().write(value)

        with Progress(stream=Stream(), interval=0.01) as progress:
            progress.stage("Slow operation")
            self.assertTrue(heartbeat.wait(2))
        self.assertFalse(progress.thread.is_alive())

    def test_agent_choice_survives_an_unchanged_return(self):
        from codex_bootstrap.agent_selection import apply_choice, candidates
        from codex_bootstrap.bootstrap import bootstrap

        bootstrap(self.root, seed_only=True)
        catalog = candidates(self.root, ".", "language-rust", offline=True)
        lock = apply_choice(
            self.root,
            catalog["catalog_id"],
            catalog["candidates"][0]["id"],
            "Deliberate Rust guide choice",
        )
        self.assertEqual(bootstrap(self.root, seed_only=True), lock)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "Cargo.toml").write_text('[package]\nname="demo"\nversion="0.1.0"\n')

    def test_seed_does_not_discover_inventory_or_download_tools(self):
        from codex_bootstrap.bootstrap import bootstrap

        with (
            patch(
                "codex_bootstrap.proposal.local_skill_paths",
                side_effect=AssertionError("inventory"),
            ),
            patch("codex_bootstrap.proposal.discover", side_effect=AssertionError("network")),
            patch(
                "codex_bootstrap.token_tools.install_rtk",
                side_effect=AssertionError("tool download"),
            ),
        ):
            lock = bootstrap(self.root, seed_only=True)
        self.assertTrue(all(s["source"] == "bundled" for s in lock["skills"]))

    def test_agent_choice_is_explicit_persisted_and_integrity_checked(self):
        from codex_bootstrap.agent_selection import apply_choice, candidates
        from codex_bootstrap.bootstrap import bootstrap, verify_lock

        bootstrap(self.root, offline=True)
        catalog = candidates(self.root, ".", "language-rust", offline=True)
        chosen = next(c for c in catalog["candidates"] if c["source"] == "bundled")
        with self.assertRaises(ValueError):
            apply_choice(self.root, catalog["catalog_id"], "invented", "Because it fits")
        lock = apply_choice(
            self.root, catalog["catalog_id"], chosen["id"], "Matches Rust ownership work"
        )
        self.assertEqual(
            lock["agent_choices"]["language-rust"]["reason"], "Matches Rust ownership work"
        )
        self.assertEqual(verify_lock(self.root), lock)
        (self.root / "Cargo.toml").write_text('[package]\nname="changed"\nversion="0.2.0"\n')
        with self.assertRaisesRegex((ValueError, RuntimeError), "manifest"):
            apply_choice(self.root, catalog["catalog_id"], chosen["id"], "Stale choice")

    def test_progress_writes_stderr_and_reports_failure(self):
        from codex_bootstrap.progress import Progress

        stream = io.StringIO()
        with self.assertRaises(ValueError):
            with Progress(stream=stream) as progress:
                progress.stage("Reading manifests")
                raise ValueError("private content must not be logged")
        self.assertIn("Reading manifests", stream.getvalue())
        self.assertIn("failed", stream.getvalue())
        self.assertNotIn("private content", stream.getvalue())
