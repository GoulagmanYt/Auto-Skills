"""Atomic first publication and refresh with a journal and the lock as commit marker."""

import base64
import hashlib
import json

from .fs import atomic_write, confined, digest, json_text


def encoded(value):
    return base64.b64encode(value).decode() if value is not None else None


def decoded(value):
    return base64.b64decode(value, validate=True) if value is not None else None


def recover(root, verify):
    path = confined(root, ".codex/bootstrap-journal.json")
    if not path.exists():
        return
    journal = json.loads(path.read_text(encoding="utf-8"))
    version = journal.get("schema_version")
    if version not in {1, 2}:
        raise ValueError("invalid bootstrap recovery journal")
    lock_path = confined(root, ".codex/skills-lock.json")
    current_lock = lock_path.read_bytes() if lock_path.exists() else None
    committed = current_lock is not None and (
        version == 1 or hashlib.sha256(current_lock).hexdigest() == journal["new_lock_sha256"]
    )
    if committed:
        verify(root)
        path.unlink()
        return
    previous_lock = decoded(journal.get("previous_lock"))
    if version == 2 and current_lock != previous_lock:
        raise ValueError("recovery would overwrite a later lock edit")
    restore = []
    for relative, entry in journal["files"].items():
        if not (
            relative in {"AGENTS.md", ".codexignore"}
            or relative.startswith((".codex/", ".agents/skills/"))
        ):
            raise ValueError("invalid recovery destination")
        if relative in {
            ".codex/skills-lock.json",
            ".codex/bootstrap-journal.json",
            ".codex/bootstrap.mutex",
        }:
            raise ValueError("reserved recovery destination")
        target = confined(root, relative)
        before = decoded(entry["before"])
        before_hash = hashlib.sha256(before).hexdigest() if before is not None else None
        now = digest(target) if target.is_file() else None
        if target.exists() and not target.is_file():
            raise ValueError("recovery destination is not a regular file")
        if now not in {entry.get("after"), before_hash}:
            raise ValueError(f"recovery would overwrite a later edit: {relative}")
        restore.append((target, before, entry.get("mode", 0o644)))
    for target, before, mode in reversed(restore):
        if before is None:
            target.unlink(missing_ok=True)
        else:
            atomic_write(target, before, executable=bool(mode & 0o111))
    if version == 2 and previous_lock is not None:
        atomic_write(lock_path, previous_lock)
    path.unlink()


def publish(root, writes, deletes, lock, *, previous=None, executable=(), verify=None):
    """writes maps repository-relative names to bytes; only owned files may be replaced."""
    previous_files = (previous or {}).get("files", {})
    paths = set(writes) | set(deletes)
    if set(writes) & set(deletes):
        raise ValueError("transaction writes and deletes overlap")
    for relative in paths:
        target = confined(root, relative)
        if target.exists() and not target.is_file():
            raise ValueError(f"destination is not a regular file: {relative}")
        if (
            target.exists()
            and relative in previous_files
            and digest(target) != previous_files[relative]
        ):
            raise ValueError(f"integrity failure before publication: {relative}")
        if target.exists() and relative.startswith(
            (".agents/skills/", ".codex/skills/", ".codex/bin/", ".codex/plugins/")
        ):
            if relative not in previous_files:
                raise ValueError(f"refusing to overwrite an unowned artifact: {relative}")
    lock_path = confined(root, ".codex/skills-lock.json")
    old_lock = lock_path.read_bytes() if lock_path.exists() else None
    if previous is not None and (old_lock is None or json.loads(old_lock) != previous):
        raise ValueError("lock changed before publication")
    lock_bytes = json_text(lock).encode()
    entries = {}
    for relative in sorted(paths):
        target = confined(root, relative)
        entries[relative] = {
            "before": encoded(target.read_bytes() if target.exists() else None),
            "after": hashlib.sha256(writes[relative]).hexdigest() if relative in writes else None,
            "mode": target.stat().st_mode & 0o777 if target.exists() else 0o644,
        }
    journal_path = confined(root, ".codex/bootstrap-journal.json")
    atomic_write(
        journal_path,
        json_text(
            {
                "schema_version": 2,
                "files": entries,
                "previous_lock": encoded(old_lock),
                "new_lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
            }
        ),
    )
    published = False
    try:
        for relative, content in writes.items():
            atomic_write(confined(root, relative), content, executable=relative in executable)
        for relative in deletes:
            confined(root, relative).unlink(missing_ok=True)
        atomic_write(lock_path, lock_bytes)
        published = True
        if verify is not None:
            verify(root)
        journal_path.unlink()
    except BaseException:
        if not published:
            recover(root, verify or (lambda root: None))
        raise
