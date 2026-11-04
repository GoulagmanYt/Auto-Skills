"""Conservative, byte-preserving reversal of owned repository artifacts."""

import hashlib
import json
import os
from pathlib import Path

from .fs import atomic_write, confined, digest, repo_mutex
from .transaction import decoded, encoded

STATE = ".codex/original-state.json"
AGENTS_BEGIN = b"<!-- codex-auto-bootstrap:v1:begin -->"
AGENTS_END = b"<!-- codex-auto-bootstrap:v1:end -->"
IGNORE_BEGIN = b"# >>> codex-auto-bootstrap ignore >>>"
IGNORE_END = b"# <<< codex-auto-bootstrap ignore <<<"


def snapshot(path):
    if path.exists() and not path.is_file():
        raise ValueError(f"destination is not a regular file: {path.name}")
    return {
        "before": encoded(path.read_bytes() if path.exists() else None),
        "mode": path.stat().st_mode & 0o7777 if path.exists() else 0o644,
    }


def restore(path, data, mode):
    if data is None:
        path.unlink(missing_ok=True)
    else:
        atomic_write(path, data)
        os.chmod(path, mode)


def remove_block(data, begin, end, *, prepend=False):
    """Remove exactly one complete managed block and its own separator."""
    if begin not in data and end not in data:
        return data
    if data.count(begin) != 1 or data.count(end) != 1:
        raise ValueError("ambiguous managed block; preserve file for manual review")
    start = data.index(begin)
    end_index = data.index(end)
    finish = end_index + len(end)
    if end_index < start:
        raise ValueError("invalid managed block")
    if start and data[start - 1 : start] != b"\n":
        raise ValueError("managed block is not on a line boundary")
    if data[finish : finish + 2] == b"\r\n":
        finish += 2
    elif data[finish : finish + 1] == b"\n":
        finish += 1
    elif finish != len(data):
        raise ValueError("managed block is not on a line boundary")
    if prepend:
        if data[finish : finish + 1] == b"\n":
            finish += 1
    elif start and data[start - 1 : start] == b"\n":
        start -= 1
    return data[:start] + data[finish:]


def owned_repository_path(relative):
    return relative in {
        "AGENTS.md",
        ".codexignore",
        ".codex/config.toml",
        ".codex/bootstrap.config.toml",
        ".codex/bootstrap-report.json",
        ".codex/profile.json",
        STATE,
        ".codex/original/AGENTS.md",
    } or relative.startswith(
        (".codex/bin/", ".codex/skills/", ".codex/plugins/", ".codex/tools/", ".agents/skills/")
    )


def uninstall_repository(root, *, dry_run=False):
    root = Path(root).resolve()
    lock_path = confined(root, ".codex/skills-lock.json")
    if not lock_path.exists():
        return {"status": "not-installed", "target": str(root), "conflicts": [], "actions": []}
    # Dry runs must not even create a mutex. Existing installations already have one.
    if dry_run:
        return _uninstall(root, dry_run=True)
    with repo_mutex(root):
        return _uninstall(root, dry_run=False)


def _uninstall(root, *, dry_run):
    lock_path = confined(root, ".codex/skills-lock.json")
    lock = json.loads(lock_path.read_bytes())
    if lock.get("schema_version") != 1 or not isinstance(lock.get("files"), dict):
        raise ValueError("invalid skills lock schema")
    files = lock["files"]
    for relative in files:
        if not owned_repository_path(relative):
            raise ValueError(f"refusing to delete unowned artifact: {relative}")
        confined(root, relative)
    state = {}
    if STATE in files:
        state_path = confined(root, STATE)
        if not state_path.is_file() or digest(state_path) != files[STATE]:
            raise ValueError("original-state backup integrity failure")
        document = json.loads(state_path.read_bytes())
        if document.get("schema_version") != 1:
            raise ValueError("invalid original-state backup")
        state = document["files"]
        if set(state) != {"AGENTS.md", ".codexignore", ".codex/config.toml"}:
            raise ValueError("invalid original-state destinations")
    plans, conflicts = {}, []
    for relative, expected in files.items():
        path = confined(root, relative)
        if not path.exists():
            continue
        if not path.is_file():
            conflicts.append(relative + ": not a regular file")
            continue
        data = path.read_bytes()
        unchanged = hashlib.sha256(data).hexdigest() == expected
        entry = state.get(relative)
        if unchanged and entry is not None:
            plans[relative] = (decoded(entry["before"]), entry["mode"])
        elif relative in {"AGENTS.md", ".codexignore"}:
            try:
                if relative == "AGENTS.md":
                    cleaned = remove_block(data, AGENTS_BEGIN, AGENTS_END, prepend=True)
                elif IGNORE_BEGIN in data:
                    cleaned = remove_block(data, IGNORE_BEGIN, IGNORE_END)
                else:
                    # Legacy installations have no exact original snapshot. Only
                    # remove the known trailing generated ignore text.
                    from .token_tools import IGNORE

                    suffix = IGNORE.encode()
                    if not data.endswith(suffix):
                        raise ValueError("legacy ignore ownership cannot be established")
                    cleaned = data[: -len(suffix)]
                if cleaned == data and not unchanged:
                    raise ValueError("managed block missing from edited file")
                plans[relative] = (
                    None if not cleaned and entry and entry["before"] is None else cleaned,
                    path.stat().st_mode & 0o7777,
                )
            except ValueError as exc:
                conflicts.append(f"{relative}: {exc}")
        elif unchanged:
            plans[relative] = (None, 0o644)
        else:
            conflicts.append(relative + ": modified artifact")
    result = {
        "status": "conflict" if conflicts else ("dry-run" if dry_run else "uninstalled"),
        "target": str(root),
        "conflicts": conflicts,
        "actions": sorted(plans),
    }
    if dry_run or conflicts:
        return result
    # Keep the lock and backups until all ordinary artifacts have been processed.
    order = sorted(plans, key=lambda p: p in {STATE, ".codex/original/AGENTS.md"})
    before = {relative: snapshot(confined(root, relative)) for relative in order}
    try:
        for relative in order:
            restore(confined(root, relative), *plans[relative])
        lock_path.unlink()
    except BaseException:
        for relative, entry in before.items():
            restore(confined(root, relative), decoded(entry["before"]), entry["mode"])
        raise
    # Remove empty owned directories only; unknown files are always retained.
    directories = {confined(root, relative).parent for relative in plans}
    for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        while directory != root and directory.is_relative_to(root):
            try:
                directory.rmdir()
            except OSError:
                break
            directory = directory.parent
    return result
