"""Per-test user/cache isolation, including tests which override setUp()."""

import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from tools.verify_native_install import isolated_environment


class IsolatedTestCase(unittest.TestCase):
    """Unit fixtures never depend on the contributor's skills, config or network."""

    def run(self, result=None):
        with (
            tempfile.TemporaryDirectory(prefix="auto-skills-unit-") as temporary,
            ExitStack() as stack,
        ):
            home = Path(temporary).resolve()
            environment = isolated_environment(home)
            # rustc can be a rustup proxy: retain the installed toolchain location,
            # while HOME/Codex configuration and all build outputs stay isolated.
            environment.setdefault("RUSTUP_HOME", str(Path.home() / ".rustup"))
            admin_roots = {
                Path("/etc/codex/skills"),
                Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "codex/skills",
            }
            for key in list(environment):
                if key.startswith("CODEX_"):
                    environment.pop(key)
            environment.update(
                CODEX_HOME=str(home / ".codex"),
                CODEX_BOOTSTRAP_CACHE=str(home / "cache"),
                CODEX_BOOTSTRAP_OFFLINE="1",
            )
            stack.enter_context(patch.dict(os.environ, environment, clear=True))
            stack.enter_context(patch.object(Path, "home", return_value=home))
            from codex_bootstrap.config import skill_roots

            stack.enter_context(
                patch(
                    "codex_bootstrap.config.skill_roots",
                    side_effect=lambda *a, **kw: [
                        p for p in skill_roots(*a, **kw) if p not in admin_roots
                    ],
                )
            )
            stack.enter_context(
                patch(
                    "socket.socket.connect",
                    side_effect=AssertionError("network forbidden in unit tests"),
                )
            )
            return super().run(result)
