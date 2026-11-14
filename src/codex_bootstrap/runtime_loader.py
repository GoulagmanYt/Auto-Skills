"""Stable, standard-library-only loader for immutable installed package versions.

The installer copies this module next to a .pth file. It must never import the
bootstrap package: selection happens before that package is imported.
"""

import json
import os
import re
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

_held = threading.local()


def state_directory(base):
    base = Path(base).resolve()
    path = base.parent / (base.name + "-state")
    if path.is_symlink() or (path.exists() and path.resolve() != path):
        raise ValueError("update state directory cannot be a link")
    return path


@contextmanager
def file_mutex(path, timeout=30):
    path = Path(path)
    key = str(path.absolute())
    held = getattr(_held, "paths", set())
    if key in held:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ValueError("update lock cannot be a link")
    with path.open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("installation is busy") from None
                time.sleep(0.05)
        _held.paths = held | {key}
        try:
            yield
        finally:
            _held.paths = held
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


@contextmanager
def installation_mutex(base, timeout=30):
    with file_mutex(state_directory(base) / "installation.lock", timeout):
        yield


def activate(base):
    if os.environ.get("CODEX_BOOTSTRAP_DISABLE_RUNTIME") == "1":
        return
    try:
        base = Path(base).resolve()
        pinned = os.environ.get("CODEX_BOOTSTRAP_RUNTIME")
        if pinned == "base":
            return
        if pinned:
            if not re.fullmatch(r"venv/versions/[0-9a-f]{40}", pinned):
                return
            expected = pinned
        else:
            # Hooks/children of this process must retain this choice after updates.
            os.environ["CODEX_BOOTSTRAP_RUNTIME"] = "base"
            record = base / "installation.json"
            if record.is_symlink() or record.stat().st_size > 16_000_000:
                return
            data = json.loads(record.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 2:
                return
            revision = data.get("source_commit", "")
            if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
                return
            expected = "venv/versions/" + revision
            if data.get("runtime_path") != expected:
                return
        target = (base / expected).resolve()
        if target.is_relative_to(base) and (target / "codex_bootstrap/__init__.py").is_file():
            sys.path.insert(0, str(target))
            os.environ["CODEX_BOOTSTRAP_RUNTIME"] = expected
    except (OSError, ValueError, TypeError, RuntimeError):
        # A broken optional pointer must not prevent the known base version loading.
        return
