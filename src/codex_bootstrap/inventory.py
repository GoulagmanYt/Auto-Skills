"""Bounded local instructions and content-addressed, pinned shared bundles.

Reading and copying instructions never executes their resources. Cached bundles
remain untrusted and pass the same eligibility checks as a fresh download.
"""

import base64
import hashlib
import json
import os
import re
from dataclasses import asdict
from pathlib import Path

from .discovery import REGISTRIES, infer_slot, normalize_resources
from .fs import atomic_write, json_text
from .github import default_cache_dir, safe_resource_path
from .selection import Candidate, rejection, select

MAX_SKILLS = 512
MAX_FILES = 80
MAX_BYTES = 2_000_000
LICENSES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "CC0-1.0"}


def local_skill_paths(root, cwd=None, owned=()):
    """Inventory authorized user/admin/repository roots, excluding owned copies.

    The broader native exclusion scan can contain resolved aliases and ancestors
    above the Git root. Those are not authorization to copy arbitrary directories.
    """
    from .config import external_skills, skill_roots

    root = Path(root).resolve()
    directories = [p.absolute() for p in skill_roots(root, cwd)]
    return [
        p
        for p in map(Path, external_skills(root, cwd))
        if any(p.absolute().is_relative_to(folder) for folder in directories)
        and (
            not p.resolve().is_relative_to(root)
            or p.resolve().relative_to(root).as_posix() not in owned
        )
    ]


def allowed_repositories():
    """Optional user-global policy; repository/remote instructions cannot widen it."""
    from .automatic_policy import automatic_policy

    sources = automatic_policy().get("repositories", REGISTRIES)
    if (
        not isinstance(sources, list)
        or len(sources) > 32
        or any(not isinstance(s, str) or not re.fullmatch(r"[\w.-]+/[\w.-]+", s) for s in sources)
    ):
        raise ValueError("invalid automatic repository allowlist")
    return set(sources)


def admissible_remote(candidate):
    if candidate.repository not in allowed_repositories():
        return "source is outside the user-global automatic allowlist"
    if not re.fullmatch(r"[0-9a-f]{40}", candidate.commit):
        return "remote commit is not pinned"
    if candidate.license not in LICENSES:
        return "license is missing or outside the automatic redistribution policy"
    return None


def local_candidate(path, profile, slots):
    path = Path(path).absolute()
    # Do not follow links while copying executable/resource bundles.
    if any(p.is_symlink() for p in (path, *path.parents)) or path.resolve() != path:
        raise ValueError("linked local bundle is not copied automatically")
    if path.stat().st_size > 24_000:
        raise ValueError("local skill exceeds instruction budget")
    text = path.read_text(encoding="utf-8-sig")
    if not text.startswith("---\n"):
        raise ValueError("missing skill front matter")
    slot = infer_slot(path.parent.name, text, slots, profile)
    if not slot:
        return None
    name = re.search(r"(?m)^name:\s*[\"']?([\w-]+)", text)
    constraint = re.search(
        r"(?m)^(?:x-bootstrap-compatibility|compatibility):\s*(\{[^\n]+\})", text
    )
    compatibility = json.loads(constraint[1]) if constraint else {}
    if not isinstance(compatibility, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in compatibility.items()
    ):
        raise ValueError("invalid local compatibility metadata")
    candidate = Candidate(
        slot=slot,
        name=name[1] if name else slot,
        body=text,
        source="local",
        origin_path=str(path.resolve()),
        compatibility=compatibility,
        license="local-use",
        declared_slot=bool(re.search(r"(?m)^(?:x-bootstrap-slot|slot):", text)),
    )
    reason = rejection(candidate, profile)
    if reason:
        raise ValueError(reason)
    resources, size, visited = {}, 0, 0
    for current, dirs, files in os.walk(path.parent, followlinks=False):
        visited += 1
        if visited > 256:
            raise ValueError("local directory budget exceeded")
        folder = Path(current)
        if any((folder / name).is_symlink() for name in dirs):
            raise ValueError("linked local resource rejected")
        dirs[:] = sorted(d for d in dirs if d not in {".git", "node_modules", ".venv"})
        for name in sorted(files):
            resource = folder / name
            if resource == path:
                continue
            relative = resource.relative_to(path.parent).as_posix()
            safe_resource_path(relative)
            if resource.is_symlink() or not resource.is_file():
                raise ValueError("linked local resource rejected")
            size += resource.stat().st_size
            if len(resources) >= MAX_FILES or size > MAX_BYTES:
                raise ValueError("local resource budget exceeded")
            resources[relative] = resource.read_bytes()
    text, resources = normalize_resources(text, resources)
    candidate.body, candidate.files = text, resources
    return candidate


def bundle_payload(candidate):
    record = asdict(candidate)
    record["files"] = {k: base64.b64encode(v).decode() for k, v in candidate.files.items()}
    for key in ("required_tools", "technologies", "executable_files"):
        record[key] = sorted(record[key])
    return record


def store_bundle(candidate, cache_dir=None):
    try:
        return _store_bundle(candidate, cache_dir)
    except OSError:
        # Shared caching is an optimization, never an installation prerequisite.
        return False


def _store_bundle(candidate, cache_dir=None):
    if candidate.source != "github" or admissible_remote(candidate):
        return
    record = bundle_payload(candidate)
    payload = json_text(record)
    sha = hashlib.sha256(payload.encode()).hexdigest()
    directory = Path(cache_dir or default_cache_dir()) / "bundles-v1"
    directory.mkdir(parents=True, exist_ok=True)
    # Atomic content-addressed publication is idempotent under concurrent writers.
    atomic_write(
        directory / (sha + ".json"),
        json_text({"schema_version": 1, "sha256": sha, "candidate": record}),
    )
    # Bound owned immutable cache entries; never remove unknown files.
    entries = []
    for path in directory.glob("[0-9a-f]" * 64 + ".json"):
        try:
            state = path.stat()
            entries.append((state.st_mtime_ns, state.st_size, path))
        except OSError:
            continue
    entries.sort()
    total = sum(size for _, size, _ in entries)
    while entries and (len(entries) > 256 or total > 64_000_000):
        _, size, old = entries.pop(0)
        try:
            total -= size
            old.unlink(missing_ok=True)
        except OSError:
            pass
    return True


def inventory(profile, paths, slots, cache_dir=None):
    candidates, rejected = [], []
    shared_hits = 0
    directory = Path(cache_dir or default_cache_dir()) / "bundles-v1"
    for path in sorted(directory.glob("*.json"))[:256]:
        try:
            if path.is_symlink() or path.stat().st_size > 3_000_000:
                raise ValueError("shared bundle exceeds budget or is linked")
            value = json.loads(path.read_text(encoding="utf-8"))
            record = value["candidate"]
            sha = hashlib.sha256(json_text(record).encode()).hexdigest()
            if value.get("schema_version") != 1 or sha != value["sha256"] or path.stem != sha:
                raise ValueError("shared bundle integrity failure")
            if record.get("slot") not in slots:
                continue
            record["files"] = {
                k: base64.b64decode(v, validate=True) for k, v in record["files"].items()
            }
            if (
                len(record["files"]) > MAX_FILES
                or sum(map(len, record["files"].values())) > MAX_BYTES
            ):
                raise ValueError("shared resource budget exceeded")
            for name in record["files"]:
                safe_resource_path(name)
            for key in ("required_tools", "technologies", "executable_files"):
                record[key] = set(record[key])
            candidate = Candidate(**record)
            reason = admissible_remote(candidate) or rejection(candidate, profile)
            if candidate.source != "github" or reason:
                raise ValueError(reason or "invalid cached source")
            candidates.append(candidate)
            shared_hits += 1
        except (OSError, ValueError, TypeError, KeyError) as exc:
            rejected.append({"source": "shared-cache", "reason": str(exc)[:180]})
    seen = set()
    for path in sorted(map(Path, paths))[:MAX_SKILLS]:
        if path.resolve() in seen:
            continue
        seen.add(path.resolve())
        try:
            candidate = local_candidate(path, profile, slots)
            if candidate is None:
                continue
            reason = rejection(candidate, profile)
            if reason:
                raise ValueError(reason)
            candidates.append(candidate)
        except (OSError, ValueError, TypeError) as exc:
            rejected.append({"source": "local", "path": str(path), "reason": str(exc)[:180]})
    # Prefer an admissible local copy to an equivalent cached remote bundle.
    local, _ = select([c for c in candidates if c.source == "local"], profile)
    covered = {c.slot for c in local}
    shared, _ = select(
        [c for c in candidates if c.source == "github" and c.slot not in covered], profile
    )
    return local + shared, {"scanned": len(seen), "shared_hits": shared_hits, "rejected": rejected}
