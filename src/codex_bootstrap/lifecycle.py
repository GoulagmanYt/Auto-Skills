"""Manifest-sensitive slot planning; unchanged pinned skills and tools are reused."""

import hashlib
from dataclasses import fields

from .fs import confined, json_text
from .profile import manifest_fingerprint
from .proposal import SELECTION_VERSION, candidate_record, scoped_profiles, selection_plan, slot_key
from .selection import Candidate, rejection
from .transaction import publish


def refresh_tools(root, lock, plan, *, offline=False, cache_dir=None):
    """Reuse pinned tools; install only newly requested tools and retire owned extras."""
    import shutil
    import tempfile
    from pathlib import Path

    from .automatic_policy import optional_tools
    from .github import GitHub
    from .token_tools import install_token_tools

    wanted = {item["name"] for item in plan}
    old = {item["name"]: item for item in lock["tools"]}
    added = wanted - set(old)
    added |= {
        name
        for name in wanted & optional_tools()
        if name in old and old[name]["status"] == "deferred" and not offline
    }
    removed = set(old) - wanted - ({"node"} if "repomix" in wanted else set())
    writes, executable = {}, set()
    tools = [item for item in lock["tools"] if item["name"] not in removed | added]
    if added:
        stage = Path(tempfile.mkdtemp(prefix=".bootstrap-tools-", dir=root / ".codex"))
        try:
            installed = install_token_tools(
                stage, offline=offline, github=GitHub(cache_dir=cache_dir), enabled=added
            )
            tools.extend(
                item for item in installed if item["name"] in added or item["name"] not in old
            )
            for path in stage.rglob("*"):
                if path.is_file() and not path.is_symlink():
                    relative = ".codex/" + path.relative_to(stage).as_posix()
                    writes[relative] = path.read_bytes()
                    if path.stat().st_mode & 0o111:
                        executable.add(relative)
        finally:
            if not stage.resolve().is_relative_to((root / ".codex").resolve()):
                raise ValueError("tool stage escaped repository")
            shutil.rmtree(stage)
    deletes = {
        relative
        for relative in lock["files"]
        if any(
            relative.startswith(f".codex/plugins/{name}/")
            or relative == f".codex/bin/{name}"
            or relative.startswith(f".codex/bin/{name}.")
            or relative.startswith(f".codex/bin/{name}-")
            for name in removed
        )
    }
    return tools, writes, executable, deletes, bool(added or removed)


def slot_inputs(profile, slot, candidate=None):
    mapping = getattr(profile, "slot_technologies", {})
    technologies = set(mapping.get(slot, []))
    if not technologies and slot.startswith(("language-", "framework-", "orm-", "database-")):
        technologies.add(slot.split("-", 1)[1])
    if candidate is not None:
        technologies.update(candidate.compatibility)
        technologies.update(getattr(candidate, "technologies", []))
    result = {
        "technologies": {key: profile.technologies.get(key) for key in sorted(technologies)},
        "resolved_versions": {
            key: getattr(profile, "resolved_versions", {}).get(key, [])
            for key in sorted(technologies)
        },
        "declarations": {
            key: getattr(profile, "technology_sources", {}).get(key, [])
            for key in sorted(technologies)
        },
        "tools": sorted(getattr(profile, "available_tools", []))
        if candidate is not None and getattr(candidate, "required_tools", [])
        else [],
    }
    manual = getattr(profile, "manual_configuration", {})
    if manual:
        # Hash only the relevant explicit intent: unrelated sibling declarations
        # must not invalidate this scope's pinned skills.
        result["manual"] = {
            "path": "auto-skills.toml",
            "technologies": {
                key: value
                for key, value in manual.get("technologies", {}).items()
                if key in technologies
            },
            "slot": slot if slot in manual.get("slots", []) else None,
        }
        if "kind" in manual:
            result["manual"]["kind"] = manual["kind"]
    return result


def load_candidate(root, entry, lock):
    prefix = entry["path"].removesuffix("SKILL.md")
    body = confined(root, entry["path"]).read_text(encoding="utf-8")
    resources, executable = {}, set()
    for relative in lock["files"]:
        if relative.startswith(prefix) and relative != entry["path"]:
            path = confined(root, relative)
            name = relative.removeprefix(prefix)
            resources[name] = path.read_bytes()
            if path.stat().st_mode & 0o111:
                executable.add(name)
    optional = {
        "required_tools": set(entry.get("required_tools", [])),
        "technologies": set(entry.get("technologies", [])),
        "declared_slot": entry.get("declared_slot", False),
        "scope": entry.get("scope", "."),
        "origin_path": entry.get("origin_path", ""),
        "license_origin": entry.get("license_origin", ""),
        "install_suffix": entry["path"].removeprefix(".codex/skills/").removesuffix("/SKILL.md"),
    }
    optional = {k: v for k, v in optional.items() if k in {f.name for f in fields(Candidate)}}
    return Candidate(
        slot=entry["slot"],
        name=entry["name"],
        body=body,
        source=entry["source"],
        repository=entry.get("repository", ""),
        commit=entry.get("commit", ""),
        remote_path=entry.get("upstream_path", ""),
        compatibility=entry.get("compatibility", {}),
        license=entry.get("license", ""),
        score=entry.get("score", 0),
        stars=entry.get("quality", {}).get("stars", 0),
        updated=entry.get("quality", {}).get("repository_updated", ""),
        files=resources,
        executable_files=executable,
        **optional,
    )


def skill_artifacts(candidates):
    writes, executable, entries = {}, set(), []
    for candidate in candidates:
        entry = candidate_record(candidate)
        suffix = candidate.install_suffix or skill_suffix(candidate.scope, candidate.slot)
        from .github import safe_resource_path

        safe_resource_path(suffix)
        entry["path"] = f".codex/skills/{suffix}/SKILL.md"
        entry["discovery_path"] = f".agents/skills/{suffix}/SKILL.md"
        entries.append(entry)
        resources = {"SKILL.md": candidate.body.encode(), **candidate.files}
        for name, content in resources.items():
            for prefix in (f".codex/skills/{suffix}/", f".agents/skills/{suffix}/"):
                relative = prefix + name
                writes[relative] = content
                if name in candidate.executable_files:
                    executable.add(relative)
    return writes, executable, entries


def reserve_skill_paths(root, candidates, previous=None):
    """Keep existing owned paths; route first-install collisions around user files."""
    entries = {
        slot_key(s.get("scope", "."), s["slot"]): s for s in (previous or {}).get("skills", [])
    }
    for candidate in candidates:
        key = slot_key(candidate.scope, candidate.slot)
        if key in entries:
            candidate.install_suffix = (
                entries[key]["path"].removeprefix(".codex/skills/").removesuffix("/SKILL.md")
            )
            continue
        suffix = skill_suffix(candidate.scope, candidate.slot)
        for attempt in range(16):
            try:
                locations = [
                    confined(root, folder + suffix)
                    for folder in (".codex/skills/", ".agents/skills/")
                ]
                available = all(
                    not p.exists() or (p.is_dir() and not any(p.iterdir())) for p in locations
                )
            except ValueError:
                available = False
            if available:
                candidate.install_suffix = suffix
                break
            suffix = (
                "@managed/"
                + hashlib.sha256((key + ":" + str(attempt)).encode()).hexdigest()[:16]
                + "/"
                + candidate.slot
            )
        else:
            raise ValueError("managed skill path collision budget exceeded")


def skill_suffix(scope, slot):
    if scope == ".":
        return slot
    from pathlib import PurePosixPath

    path = PurePosixPath(scope)
    if path.is_absolute() or ".." in path.parts or "\\" in scope or ":" in scope:
        raise ValueError("invalid workspace scope")
    return f"@workspaces/{scope}/{slot}"


def refresh_plan(root, lock, profile, *, force=False, preset=None):
    preset = preset or lock.get("policy", {}).get("preset", "auto")
    profiles, _ = scoped_profiles(root, profile, preset)
    entries = {slot_key(entry.get("scope", "."), entry["slot"]): entry for entry in lock["skills"]}
    wanted = {slot_key(scope, slot): (p, slot) for scope, p in profiles.items() for slot in p.slots}
    removed = set(entries) - set(wanted)
    affected, retained = set(), {}
    migrate = lock.get("selection_version") != SELECTION_VERSION
    for key, (scoped, slot) in wanted.items():
        entry = entries.get(key)
        if entry is None:
            affected.add(key)
            continue
        candidate = load_candidate(root, entry, lock)
        reason = rejection(candidate, scoped)
        if candidate.source == "github":
            from .inventory import admissible_remote

            reason = reason or admissible_remote(candidate)
        if (
            force
            or migrate
            or reason
            or lock.get("slot_inputs", {}).get(key) != slot_inputs(scoped, slot, candidate)
        ):
            affected.add(key)
        else:
            retained[key] = candidate
    return affected, removed, retained


def refresh(
    root,
    lock,
    profile,
    manifest_hashes,
    *,
    offline=False,
    force=False,
    cache_dir=None,
    preset=None,
    seed_only=False,
):
    from .bootstrap import verify_lock

    preset = preset or lock.get("policy", {}).get("preset", "auto")
    profiles, policy = scoped_profiles(root, profile, preset)
    affected, removed, retained = refresh_plan(root, lock, profile, force=force, preset=preset)
    selected, report = selection_plan(
        profile,
        offline=offline,
        slots=affected,
        cache_dir=cache_dir,
        root=root,
        preset=preset,
        seed_only=seed_only,
    )
    reserve_skill_paths(root, selected, lock)
    refreshed = {slot_key(c.scope, c.slot): c for c in selected}
    wanted = [slot_key(scope, slot) for scope, p in profiles.items() for slot in p.slots]
    ordered = [refreshed.get(key) or retained[key] for key in wanted]
    writes, executable, entries = skill_artifacts(selected)
    # Never touch unchanged content: this preserves file mtimes and avoids copying tool trees.
    writes = {
        relative: content
        for relative, content in writes.items()
        if lock["files"].get(relative) != hashlib.sha256(content).hexdigest()
    }
    obsolete_prefixes = tuple(
        entry[key].removesuffix("SKILL.md")
        for entry in lock["skills"]
        if slot_key(entry.get("scope", "."), entry["slot"]) in affected | removed
        for key in ("path", "discovery_path")
    )
    desired, _, _ = skill_artifacts(selected)
    deletes = {
        relative
        for relative in lock["files"]
        if obsolete_prefixes and relative.startswith(obsolete_prefixes) and relative not in desired
    }
    entries_by_slot = {slot_key(entry.get("scope", "."), entry["slot"]): entry for entry in entries}
    previous_entries = {slot_key(e.get("scope", "."), e["slot"]): e for e in lock["skills"]}
    new_entries = [entries_by_slot.get(key) or previous_entries[key] for key in wanted]
    tools, tool_writes, tool_executable, tool_deletes, tools_changed = refresh_tools(
        root, lock, report["tool_plan"], offline=offline or seed_only, cache_dir=cache_dir
    )
    writes.update(
        {
            name: data
            for name, data in tool_writes.items()
            if lock["files"].get(name) != hashlib.sha256(data).hexdigest()
        }
    )
    executable.update(tool_executable)
    deletes.update(tool_deletes)
    report.update(
        {
            "mode": "refresh",
            "target": str(root),
            "installed": True,
            "changes": {
                "refreshed_slots": sorted(affected),
                "removed_slots": sorted(removed),
                "retained_slots": sorted(retained),
                "tools_reinstalled": tools_changed,
            },
            "selected": [candidate_record(candidate) for candidate in ordered],
            "tools": tools,
        }
    )
    report["coverage"]["evaluated_slots"] = sorted(affected)
    report["coverage"]["remote_slots"] = [
        slot_key(c.scope, c.slot) for c in ordered if c.source == "github"
    ]
    report["coverage"]["bundled_slots"] = [
        slot_key(c.scope, c.slot) for c in ordered if c.source == "bundled"
    ]
    from .config import agents_text

    existing_agents = confined(root, "AGENTS.md").read_text(encoding="utf-8")
    updated_agents = agents_text(existing_agents).encode()
    if hashlib.sha256(updated_agents).hexdigest() != lock["files"].get("AGENTS.md"):
        writes["AGENTS.md"] = updated_agents
    writes[".codex/profile.json"] = json_text(profile.to_dict()).encode()
    writes[".codex/bootstrap-report.json"] = json_text(report).encode()
    updated = dict(lock)
    updated["agent_choices"] = {
        k: v for k, v in lock.get("agent_choices", {}).items() if k not in affected | removed
    }
    for entry in new_entries:
        choice = updated["agent_choices"].get(slot_key(entry.get("scope", "."), entry["slot"]))
        if choice:
            entry["reason"] = choice["reason"]
            entry["quality"]["method"] = "agent decision after deterministic eligibility checks"
    report["selected"] = new_entries
    report["agent_choices"] = updated["agent_choices"]
    writes[".codex/bootstrap-report.json"] = json_text(report).encode()
    updated.update(
        {
            "manifest_hashes": manifest_hashes,
            "selection_version": SELECTION_VERSION,
            "policy": policy,
            "tool_plan": report["tool_plan"],
            "tools": tools,
            "skills": new_entries,
            "slot_inputs": {
                slot_key(c.scope, c.slot): slot_inputs(profiles[c.scope], c.slot, c)
                for c in ordered
            },
        }
    )
    from datetime import UTC, datetime

    updated["updated_at"] = datetime.now(UTC).isoformat()
    updated["files"] = {
        relative: sha for relative, sha in lock["files"].items() if relative not in deletes
    }
    updated["files"].update(
        {relative: hashlib.sha256(content).hexdigest() for relative, content in writes.items()}
    )
    updated["degraded"] = (
        offline
        or bool(report["discovery"].get("errors"))
        or bool(report["discovery"].get("degraded"))
        or (bool(lock.get("degraded")) and bool(retained))
        or not report["coverage"]["remote_slots"]
        or any(t["status"] != "installed" for t in tools)
    )
    report["degraded"] = updated["degraded"]
    writes[".codex/bootstrap-report.json"] = json_text(report).encode()
    updated["files"][".codex/bootstrap-report.json"] = hashlib.sha256(
        writes[".codex/bootstrap-report.json"]
    ).hexdigest()
    if manifest_hashes != manifest_fingerprint(root):
        raise RuntimeError("manifests changed during refresh; no new configuration was published")
    publish(
        root, writes, deletes, updated, previous=lock, executable=executable, verify=verify_lock
    )
    return updated  # Publication has completed its full integrity verification.


def status(root, lock, profile, manifest_hashes, *, preset=None, offline=False):
    from .automatic_policy import optional_tools
    from .policy import tool_plan

    preset = preset or lock.get("policy", {}).get("preset", "auto")
    _, policy = scoped_profiles(root, profile, preset)
    affected, removed, retained = refresh_plan(root, lock, profile, preset=preset)
    changed = lock.get("manifest_hashes") != manifest_hashes
    changed = (
        changed
        or lock.get("policy") != policy
        or lock.get("tool_plan") != tool_plan(profile, policy)
        or (
            not offline
            and any(
                t["name"] in optional_tools() and t["status"] == "deferred" for t in lock["tools"]
            )
        )
    )
    return {
        "status": "stale" if changed or affected or removed else "current",
        "manifest_changes": sorted(
            path
            for path in set(lock.get("manifest_hashes", {})) | set(manifest_hashes)
            if lock.get("manifest_hashes", {}).get(path) != manifest_hashes.get(path)
        ),
        "affected_slots": sorted(affected),
        "removed_slots": sorted(removed),
        "retained_slots": sorted(retained),
        "degraded": lock.get("degraded", False),
    }
