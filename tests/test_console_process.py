import json
import os
import queue
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from suite_support import IsolatedTestCase


class ConsoleProcessTests(IsolatedTestCase):
    @unittest.skipIf(os.name == "nt", "POSIX process-group termination")
    def test_shutdown_kills_a_child_which_ignores_sigterm(self):
        from codex_bootstrap.console_process import spawn_console

        code = "import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);print('READY',flush=True);time.sleep(60)"
        child = spawn_console([sys.executable, "-u", "-c", code], env=None, cwd=None, size=(80, 24))
        try:
            self.assertIn(b"READY", child.read())
            start = time.monotonic()
            child.close()
            self.assertLess(time.monotonic() - start, 3)
            self.assertEqual(child.poll(), 137)
        finally:
            child.close()

    def test_child_exit_with_open_panel_restores_terminal_protocols(self):
        from codex_bootstrap.console_process import spawn_console

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".codex").mkdir()
            (root / ".codex/skills-lock.json").write_text('{"skills":[]}')
            fake = "import os,time;os.write(1,b'\\x1b[?2004h');time.sleep(0.2);os.write(1,b'\\x1b[?2004l')"
            script = "import os,sys; from pathlib import Path; from codex_bootstrap.terminal_dashboard import run_terminal; sys.exit(run_terminal([sys.executable,'-u','-c',sys.argv[2]],Path(sys.argv[1]),env=dict(os.environ),start_open=True))"
            child = spawn_console(
                [sys.executable, "-u", "-c", script, str(root), fake],
                env=None,
                cwd=None,
                size=(100, 30),
            )
            chunks = []

            def drain():
                while data := child.read():
                    chunks.append(data)

            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
            deadline = time.monotonic() + 10
            try:
                while child.poll() is None and time.monotonic() < deadline:
                    reader.join(timeout=0.1)
                self.assertEqual(child.poll(), 0)
                child.close()
                reader.join(timeout=2)
                output = b"".join(chunks)
                self.assertIn(b"AUTO-SKILLS", output)
                self.assertIn(b"\x1b[?2004l", output)
            finally:
                child.close()

    def test_dashboard_round_trip_preserves_native_process_and_draft_input(self):
        from codex_bootstrap.console_process import spawn_console

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".codex").mkdir()
            (root / ".codex/skills-lock.json").write_text(json.dumps({"skills": []}))
            fake = "import sys; print('CODEX_READY',flush=True); answer=input(); print('ANSWER='+answer,flush=True); sys.exit(7)"
            script = "import os,sys; from pathlib import Path; from codex_bootstrap.terminal_dashboard import run_terminal; sys.exit(run_terminal([sys.executable,'-u','-c',sys.argv[2]],Path(sys.argv[1]),env=dict(os.environ),inventory_command=[sys.executable,'-c','print({})']))"
            child = spawn_console(
                [sys.executable, "-u", "-c", script, str(root), fake],
                env=dict(os.environ),
                cwd=None,
                size=(100, 30),
            )
            chunks = queue.Queue()

            def drain():
                while data := child.read():
                    chunks.put(data)

            reader = threading.Thread(target=drain, daemon=True)
            reader.start()
            transcript = b""

            def until(marker):
                nonlocal transcript
                deadline = time.monotonic() + 15
                while marker not in transcript and time.monotonic() < deadline:
                    try:
                        transcript += chunks.get(timeout=0.2)
                    except queue.Empty:
                        pass
                self.assertIn(marker, transcript)

            try:
                until(b"F9 opens skills")
                child.write(b"draft")
                child.write(b"\x1b[120;67;0;1;0;1_" if os.name == "nt" else b"\x1b[20~")
                until(b"AUTO-SKILLS")
                child.write(b"q")
                child.write(b"Z\r")
                until(b"ANSWER=draftZ")
                deadline = time.monotonic() + 5
                while child.poll() is None and time.monotonic() < deadline:
                    try:
                        transcript += chunks.get(timeout=0.1)
                    except queue.Empty:
                        pass
                self.assertEqual(child.poll(), 7)
            finally:
                child.close()
                reader.join(timeout=2)

    def test_real_pseudoterminal_input_resize_and_exit_code(self):
        from codex_bootstrap.console_process import spawn_console

        child = spawn_console(
            [
                sys.executable,
                "-u",
                "-c",
                "import sys;print('READY',flush=True);print('ANSWER='+input(),flush=True);sys.exit(7)",
            ],
            env=None,
            cwd=None,
            size=(90, 25),
        )
        output = queue.Queue()

        def drain():
            while chunk := child.read():
                output.put(chunk)

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        try:
            transcript = b""
            deadline = time.monotonic() + 15
            while b"READY" not in transcript and time.monotonic() < deadline:
                transcript += output.get(timeout=5)
            self.assertIn(b"READY", transcript)
            child.resize((80, 24))
            child.write(b"hello\r")
            while child.poll() is None and time.monotonic() < deadline:
                try:
                    transcript += output.get(timeout=0.1)
                except queue.Empty:
                    pass
            self.assertEqual(child.poll(), 7)
            child.close()
            reader.join(timeout=3)
            while not output.empty():
                transcript += output.get_nowait()
            self.assertIn(b"ANSWER=hello", transcript)
        finally:
            child.close()
