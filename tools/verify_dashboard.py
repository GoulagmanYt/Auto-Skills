"""Open and close the real Codex dashboard without sending a model prompt."""

import argparse
import json
import os
import queue
import sys
import threading
import time
from pathlib import Path

from codex_bootstrap.console_process import spawn_console


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--codex", type=Path, required=True)
    options = parser.parse_args()
    env = dict(
        os.environ,
        CODEX_BOOTSTRAP_OFFLINE="1",
        CODEX_BOOTSTRAP_REAL_CODEX=str(options.codex.absolute()),
    )
    child = spawn_console(
        [
            sys.executable,
            "-B",
            "-m",
            "codex_bootstrap",
            "--no-daemon",
            "-C",
            str(options.repo.resolve()),
        ],
        env=env,
        cwd=options.repo,
        size=(110, 35),
    )
    chunks = queue.Queue()

    def drain():
        while data := child.read():
            chunks.put(data)

    reader = threading.Thread(target=drain, daemon=True)
    reader.start()
    transcript = bytearray()
    deadline = time.monotonic() + 60

    def until(marker):
        while marker not in transcript and child.poll() is None and time.monotonic() < deadline:
            try:
                transcript.extend(chunks.get(timeout=0.2))
                del transcript[:-1_000_000]
            except queue.Empty:
                pass
        if marker not in transcript:
            raise RuntimeError("native dashboard smoke test did not reach its next screen")

    try:
        until(b"F9 opens skills")
        child.write(b"\x1b[120;67;0;1;0;1_" if os.name == "nt" else b"\x1b[20~")
        until(b"AUTO-SKILLS")
        child.write(b"2")
        until(b"Disponibilite")
        child.write(b"q")
        alive = child.poll() is None
        print(
            json.dumps(
                {"dashboard_opened": True, "plugin_tab": True, "native_alive_after_return": alive}
            )
        )
        # Only this disposable diagnostic instance is closed; no model prompt is sent.
        return 0 if alive else 1
    finally:
        child.close()
        reader.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
