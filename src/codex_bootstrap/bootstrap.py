"""Serialized first setup and manifest-sensitive refresh with immutable artifact checks."""

import hashlib
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .config import agents_text, local_config
from .fs import atomic_write, command, confined, digest, json_text, repo_mutex
from .github import GitHub
from .lifecycle import refresh, skill_artifacts, slot_inputs, status
from .profile import manifest_fingerprint, profile_repo
from .proposal import SELECTION_VERSION, scoped_profiles, selection_plan, slot_key
from .repository_uninstall import IGNORE_BEGIN, IGNORE_END, STATE, snapshot
from .token_tools import IGNORE, install_token_tools
from .transaction import publish, recover


def git_root(cwd):
    try:
        return Path(
            command(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"]).strip()
        ).resolve()
    except RuntimeError:
        return None


def verify_lock(root: Path):
    lock_path = confined(root, ".codex/skills-lock.json")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("schema_version") != 1 or not isinstance(lock.get("files"), dict):
        raise ValueError("invalid skills lock schema")
    slots = [slot_key(entry.get("scope", "."), entry["slot"]) for entry in lock.get("skills", [])]
    if not slots or len(slots) != len(set(slots)):
        raise ValueError("invalid or duplicate skill slots")
    for relative, expected in lock["files"].items():
        path = confined(root, relative)
        if not path.is_file() or digest(path) != expected:
            raise ValueError(f"integrity failure: {relative}")
    for skill in lock["skills"]:
        for key in ("path", "discovery_path"):
            if skill[key] not in lock["files"]:
                raise ValueError("skill missing from integrity manifest")
    for folder in (".codex/skills", ".agents/skills"):
        directory = confined(root, folder)
        if directory.exists():
            for path in directory.rglob("SKILL.md"):
                if path.relative_to(root).as_posix() not in lock["files"]:
                    raise ValueError("integrity failure: unlisted local skill")
    return lock


def recover_transaction(root):
    recover(root, verify_lock)


def check(root, *, preset=None):
    root = root.resolve()
    if not confined(root, ".codex/skills-lock.json").exists():
        return {"status": "uninitialized", "target": str(root)}
    lock = verify_lock(root)
    profile = profile_repo(root)
    result = status(root, lock, profile, manifest_fingerprint(root, profile), preset=preset)
    result["target"] = str(root)
    return result


def bootstrap(root: Path, *, offline=False, refresh_all=False, cache_dir=None, preset=None):
    root = root.resolve()
    if git_root(root) != root:
        raise ValueError("bootstrap target must be a Git repository root")
    with repo_mutex(root):
        recover_transaction(root)
        lock_path = confined(root, ".codex/skills-lock.json")
        previous = verify_lock(root) if lock_path.exists() else None
        if previous is None and any(
            confined(root, relative).exists() for relative in (STATE, ".codex/original/AGENTS.md")
        ):
            raise ValueError(
                "existing original backup has no ownership lock; preserve it for review"
            )
        profile = profile_repo(root)
        preset = preset or (previous or {}).get("policy", {}).get("preset", "auto")
        fingerprints = manifest_fingerprint(root, profile)
        if previous is not None:
            current = status(root, previous, profile, fingerprints, preset=preset)
            if not refresh_all and current["status"] == "current":
                return previous
            return refresh(
                root,
                previous,
                profile,
                fingerprints,
                offline=offline,
                force=refresh_all,
                cache_dir=cache_dir,
                preset=preset,
            )
        selected, report = selection_plan(
            profile, offline=offline, cache_dir=cache_dir, root=root, preset=preset
        )
        profiles, policy = scoped_profiles(root, profile, preset)
        stage = Path(tempfile.mkdtemp(prefix=".bootstrap-stage-", dir=root / ".codex"))
        try:
            tools = install_token_tools(
                stage,
                offline=offline,
                github=GitHub(cache_dir=cache_dir),
                enabled={item["name"] for item in report["tool_plan"]},
            )
            writes, executable, skills = skill_artifacts(selected)
            report.update(
                {"mode": "bootstrap", "target": str(root), "installed": True, "tools": tools}
            )
            atomic_write(stage / "bootstrap-report.json", json_text(report))
            atomic_write(stage / "profile.json", json_text(profile.to_dict()))
            atomic_write(stage / "bootstrap.config.toml", local_config())
            agents = confined(root, "AGENTS.md")
            originals = {
                relative: snapshot(confined(root, relative))
                for relative in ("AGENTS.md", ".codexignore", ".codex/config.toml")
            }
            existing = agents.read_bytes() if agents.exists() else b""
            writes["AGENTS.md"] = agents_text().encode() + (b"\n" + existing if existing else b"")
            atomic_write(
                stage / "original-state.json", json_text({"schema_version": 1, "files": originals})
            )
            if agents.exists():
                atomic_write(stage / "original/AGENTS.md", existing)
            if not confined(root, ".codex/config.toml").exists():
                atomic_write(stage / "config.toml", local_config())
            ignore_path = confined(root, ".codexignore")
            old_ignore = ignore_path.read_bytes() if ignore_path.exists() else b""
            writes[".codexignore"] = (
                old_ignore
                + (b"\n" if old_ignore else b"")
                + IGNORE_BEGIN
                + b"\n"
                + IGNORE.encode()
                + IGNORE_END
                + b"\n"
            )
            for path in stage.rglob("*"):
                if path.is_symlink():
                    path.unlink()
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    relative = ".codex/" + path.relative_to(stage).as_posix()
                    writes[relative] = path.read_bytes()
                    if path.stat().st_mode & 0o111:
                        executable.add(relative)
            lock = {
                "schema_version": 1,
                "generator": "codex-auto-bootstrap/" + __version__,
                "selection_version": SELECTION_VERSION,
                "created_at": datetime.now(UTC).isoformat(),
                "manifest_hashes": fingerprints,
                "policy": policy,
                "tool_plan": report["tool_plan"],
                "slot_inputs": {
                    slot_key(c.scope, c.slot): slot_inputs(profiles[c.scope], c.slot, c)
                    for c in selected
                },
                "skills": skills,
                "tools": tools,
                "files": {
                    relative: hashlib.sha256(data).hexdigest() for relative, data in writes.items()
                },
                "degraded": report["degraded"] or any(t["status"] != "installed" for t in tools),
            }
            if fingerprints != manifest_fingerprint(root):
                raise RuntimeError(
                    "manifests changed during bootstrap; no configuration was published"
                )
            publish(root, writes, set(), lock, executable=executable, verify=verify_lock)
            return verify_lock(root)
        finally:
            if not stage.resolve().is_relative_to((root / ".codex").resolve()):
                raise ValueError("stage escaped repository")
            shutil.rmtree(stage)
