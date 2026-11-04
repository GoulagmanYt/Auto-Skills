"""Bounded subprocesses, confined paths, atomic writes and process locking."""

import hashlib
import json
import os
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


def command(args, *, cwd=None, timeout=45, binary=False, env=None):
    result = subprocess.run(
        [str(a) for a in args],
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=timeout,
        text=not binary,
        encoding=None if binary else "utf-8",
        errors=None if binary else "replace",
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if result.returncode:
        # Do not echo stderr: a subprocess may include credentials in diagnostics.
        raise RuntimeError(f"{Path(str(args[0])).name} exited {result.returncode}")
    return result.stdout


def confined(root: Path, relative: str | Path) -> Path:
    root = root.resolve()
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts or ":" in str(relative):
        raise ValueError(f"unsafe relative path: {relative}")
    target = root / relative
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        # Junctions and symlinks within the root are also disallowed for writes.
        if cursor.is_symlink() or (cursor.exists() and cursor.resolve() != cursor):
            raise ValueError(f"redirected path: {relative}")
    if not target.resolve().is_relative_to(root):
        raise ValueError(f"path escapes repository: {relative}")
    return target


def atomic_write(path: Path, data: str | bytes, *, executable=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = data.encode("utf-8") if isinstance(data, str) else data
    fd, tmp = tempfile.mkstemp(prefix=".bootstrap-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if executable:
            os.chmod(tmp, 0o755)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def digest(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


@contextmanager
def repo_mutex(root: Path, timeout=900):
    path = confined(root, ".codex/bootstrap.mutex")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        start = time.monotonic()
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
                if time.monotonic() - start > timeout:
                    raise TimeoutError("another bootstrap is still running") from None
                time.sleep(0.1)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)
