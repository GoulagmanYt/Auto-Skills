"""Codex upgrades must remain visible through the bootstrap wrapper."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from suite_support import IsolatedTestCase

from codex_bootstrap.cli import real_codex


class CodexUpdateTests(IsolatedTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        self.standalone = self.home / ".codex/packages/standalone"
        self.old = self.standalone / "releases/0.167.1/bin/codex.exe"
        self.current = self.standalone / "current/bin/codex.exe"
        for executable in (self.old, self.current):
            executable.parent.mkdir(parents=True, exist_ok=True)
            executable.write_bytes(b"native executable")
        self.record = self.home / ".local/share/codex-auto-bootstrap/installation.json"
        self.record.parent.mkdir(parents=True)
        self.record.write_text(json.dumps({"real_codex": str(self.old)}))

    def test_legacy_record_follows_current_standalone_release(self):
        with patch.object(Path, "home", return_value=self.home):
            self.assertEqual(real_codex(), [str(self.current)])

    def test_legacy_record_recovers_after_old_release_is_removed(self):
        self.old.unlink()
        with patch.object(Path, "home", return_value=self.home):
            self.assertEqual(real_codex(), [str(self.current)])

    def test_legacy_record_retains_release_when_current_is_unavailable(self):
        self.current.unlink()
        with patch.object(Path, "home", return_value=self.home):
            self.assertEqual(real_codex(), [str(self.old)])

    def test_explicit_override_keeps_requested_release(self):
        with patch.dict("os.environ", {"CODEX_BOOTSTRAP_REAL_CODEX": str(self.old)}):
            self.assertEqual(real_codex(), [str(self.old)])

    def test_custom_executable_is_preserved(self):
        custom = self.home / "custom/codex.exe"
        custom.parent.mkdir()
        custom.write_bytes(b"custom executable")
        self.record.write_text(json.dumps({"real_codex": str(custom)}))
        with patch.object(Path, "home", return_value=self.home):
            self.assertEqual(real_codex(), [str(custom)])
