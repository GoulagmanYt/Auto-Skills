"""Selection and human-readable diagnostics without installing into a repository."""

import re
from collections import Counter
from copy import copy
from datetime import UTC, datetime
from pathlib import Path

from .catalog import bundled_candidates
from .discovery import discover
from .fs import atomic_write, json_text
from .github import default_cache_dir
from .policy import adapt_profile, policy_for, tool_plan
from .profile import profile_repo
from .selection import select

SELECTION_VERSION = 3


def slot_key(scope, slot):
    return slot if scope == "." else f"{scope}::{slot}"


def scoped_profiles(root, profile, preset="auto"):
    from .workspaces import selection_profiles

    policy = policy_for(root, profile, preset)
    profiles, scope_policies = {}, {}
    for scope, value in selection_profiles(root, profile).items():
        scoped_policy = policy if scope == "." else policy_for(root / scope, value, preset)
        if scope != "." and scoped_policy["effective"] == "documentation":
            # Scoped application pruning removes shared baseline roles. A docs
            # workspace still needs its own guide and an explicit activation scope.
            value.slots = list(dict.fromkeys([*value.slots, "documentation"]))
        profiles[scope] = adapt_profile(value, scoped_policy)
        profiles[scope].repository_kind = scoped_policy.get(
            "repository_kind", value.repository_kind
        )
        if scope != ".":
            scope_policies[scope] = scoped_policy
    if scope_policies:
        policy["scope_policies"] = scope_policies
    return profiles, policy


def candidate_record(candidate):
    record = {
        "scope": candidate.scope,
        "slot": candidate.slot,
        "name": candidate.name,
        "source": candidate.source,
        "repository": candidate.repository,
        "commit": candidate.commit,
        "upstream_path": candidate.remote_path,
        "license": candidate.license,
        "score": candidate.score,
        "compatibility": candidate.compatibility,
        "required_tools": sorted(getattr(candidate, "required_tools", [])),
        "technologies": sorted(getattr(candidate, "technologies", [])),
        "declared_slot": getattr(candidate, "declared_slot", False),
        "resource_count": len(candidate.files),
        "reason": (
            f"eligible for {candidate.slot}; "
            + (
                "technology match: " + ", ".join(sorted(candidate.technologies)) + "; "
                if candidate.technologies
                else "portable functional guidance; "
            )
            + "version/tool/policy filters passed; highest eligible slot score"
        ),
        "quality": {
            "method": "deterministic heuristics, not a semantic guarantee",
            "characters": len(candidate.body),
            "words": len(re.findall(r"\b\w+\b", candidate.body)),
            "stars": candidate.stars,
            "repository_updated": candidate.updated,
            "has_version_constraints": bool(candidate.compatibility),
            "version_limit": "constraints checked when declared; an unspecified compatibility range is not certified",
        },
    }
    if candidate.repository:
        record["url"] = (
            f"https://github.com/{candidate.repository}/blob/{candidate.commit}/{candidate.remote_path}"
        )
    return record


def selection_plan(
    profile, *, offline=False, github=None, slots=None, cache_dir=None, root=None, preset="auto"
):
    if root is not None:
        profiles, policy = scoped_profiles(root, profile, preset)
        known = {slot_key(scope, slot) for scope, p in profiles.items() for slot in p.slots}
        if slots is not None and not set(slots).issubset(known):
            raise ValueError("unknown selection slots")
        all_selected, reports = [], []
        for scope, scoped in profiles.items():
            wanted = (
                None
                if slots is None
                else {slot for slot in scoped.slots if slot_key(scope, slot) in slots}
            )
            chosen, part = selection_plan(
                scoped, offline=offline, github=github, slots=wanted, cache_dir=cache_dir
            )
            chosen = [copy(candidate) for candidate in chosen]
            for candidate in chosen:
                candidate.scope = scope
            all_selected.extend(chosen)
            reports.append((scope, part))
        report = reports[0][1]
        report["profile"] = adapt_profile(profile, policy).to_dict()
        for field in ("repository_kind", "kind_source", "manual_configuration"):
            report["profile"][field] = getattr(profiles["."], field)
        for technology in profiles["."].manual_configuration.get("technologies", {}):
            report["profile"]["technologies"][technology] = profiles["."].technologies[technology]
            report["profile"]["technology_sources"][technology] = profiles["."].technology_sources[
                technology
            ]
        for scope, scoped in profiles.items():
            for warning in scoped.warnings:
                if "auto-skills.toml:" in warning:
                    message = warning if scope == "." else f"{scope}: {warning}"
                    if message not in report["profile"]["warnings"]:
                        report["profile"]["warnings"].append(message)
        report["workspaces"] = {scope: value.to_dict() for scope, value in profiles.items()}
        report["policy"] = policy
        report["tool_plan"] = tool_plan(profile, policy)
        report["selected"] = [candidate_record(c) for c in all_selected]
        report["selection_rejections"] = [
            {**item, "scope": scope}
            for scope, part in reports
            for item in part["selection_rejections"]
        ]
        report["discovery"] = {
            "offline": offline,
            **{
                key: [entry for _, part in reports for entry in part["discovery"].get(key, [])]
                for key in ("queries", "errors", "rejected")
            },
            "workspaces": {scope: part["discovery"] for scope, part in reports},
            "remote_candidates": sum(
                part["discovery"].get("remote_candidates", 0) for _, part in reports
            ),
            "cache": dict(getattr(github, "stats", {}))
            if github is not None
            else {
                key: sum(part["discovery"].get("cache", {}).get(key, 0) for _, part in reports)
                for key in ("requests", "disk_cache_hits", "memory_cache_hits", "retries")
            },
        }
        report["coverage"] = {
            "requested_slots": [
                slot_key(scope, s)
                for scope, p in profiles.items()
                for s in p.slots
                if slots is None or slot_key(scope, s) in slots
            ],
            "uncovered": [],
            "remote_slots": [
                slot_key(c.scope, c.slot) for c in all_selected if c.source == "github"
            ],
            "bundled_slots": [
                slot_key(c.scope, c.slot) for c in all_selected if c.source == "bundled"
            ],
        }
        report["degraded"] = any(part["degraded"] for _, part in reports)
        return all_selected, report
    requested = set(profile.slots if slots is None else slots)
    if not requested.issubset(profile.slots):
        raise ValueError("unknown selection slots")
    if offline or not requested:
        remote, discovery = [], {"offline": offline, "queries": [], "errors": [], "rejected": []}
    else:
        remote, discovery = discover(profile, github, slots=requested, cache_dir=cache_dir)
    bundled = [c for c in bundled_candidates(profile) if c.slot in requested]
    selected, rejected = select(bundled + [c for c in remote if c.slot in requested], profile)
    missing = sorted(requested - {c.slot for c in selected})
    if missing:
        raise ValueError("no eligible candidate for slots: " + ", ".join(missing))
    report = {
        "schema_version": 1,
        "selection_version": SELECTION_VERSION,
        "created_at": datetime.now(UTC).isoformat(),
        "mode": "proposal",
        "profile": profile.to_dict(),
        "selected": [candidate_record(c) for c in selected],
        "selection_rejections": rejected,
        "discovery": discovery,
        "coverage": {
            "requested_slots": sorted(requested),
            "uncovered": missing,
            "remote_slots": [c.slot for c in selected if c.source == "github"],
            "bundled_slots": [c.slot for c in selected if c.source == "bundled"],
        },
        "degraded": offline
        or bool(discovery.get("errors"))
        or bool(discovery.get("degraded"))
        or not any(c.source == "github" for c in selected),
        "limitations": [
            "Compatibility and relevance filtering are conservative heuristics, not a semantic proof.",
            "Bundled skills cover slots without an eligible remote winner.",
            "No skill, binary, AGENTS.md, lock or Codex configuration is installed by propose.",
        ],
    }
    return selected, report


def propose(root: Path, *, offline=False, github=None, slots=None, cache_dir=None, preset="auto"):
    root = root.resolve()
    location = (
        Path(cache_dir or getattr(github, "cache_dir", None) or default_cache_dir())
        .expanduser()
        .resolve()
    )
    if location.is_relative_to(root):
        raise ValueError("proposal cache must be outside the target repository")
    profile = profile_repo(root)
    _, report = selection_plan(
        profile,
        offline=offline,
        github=github,
        slots=slots,
        cache_dir=location,
        root=root,
        preset=preset,
    )
    report["target"] = str(root)
    report["installed"] = False
    return report


def markdown_report(report):
    lines = [
        "# Codex skill proposal",
        "",
        f"Target: `{report.get('target', '')}`",
        "",
        f"Mode: **{report.get('mode', 'proposal')}**. Installed: **no**.",
        f"Selected: **{len(report['selected'])}**; remote: **{len(report['coverage']['remote_slots'])}**; "
        f"bundled: **{len(report['coverage']['bundled_slots'])}**; degraded: **{report['degraded']}**.",
        "",
    ]
    for source_kind, title in (
        ("bundled", "Skills intérieurs — catalogue intégré"),
        ("github", "Skills extérieurs — GitHub"),
    ):
        lines += [
            "",
            "## " + title,
            "",
            "| Workspace | Slot | Skill | Source | Motif | Score |",
            "|---|---|---|---|---|---|",
        ]
        entries = [entry for entry in report["selected"] if entry["source"] == source_kind]
        for entry in entries:
            source = (
                f"[{entry['repository']}@{entry['commit'][:12]}]({entry['url']})"
                if entry.get("url")
                else "bundled"
            )
            reason = entry["reason"].replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| `{entry.get('scope', '.')}` | `{entry['slot']}` | `{entry['name']}` | {source} | {reason} | {entry['score']} |"
            )
        if not entries:
            lines.append("| — | — | Aucun candidat retenu | — | — | — |")
    lines += [
        "",
        "La qualité et la compatibilité sont filtrées par heuristiques ; une plage de versions non déclarée n'est pas certifiée.",
        "",
        "## Outils prévus",
        "",
    ]
    lines.extend(f"- `{item['name']}` : {item['reason']}" for item in report.get("tool_plan", []))
    lines += ["", "## Versions", ""]
    lines.extend(
        f"- `{tech}`: `{version}`"
        for tech, version in sorted(report["profile"]["technologies"].items())
    )
    lines += ["", "## Rejections", ""]
    rejections = report["selection_rejections"] + report["discovery"].get("rejected", [])
    lines.extend(
        f"- `{entry.get('name', entry.get('path', entry.get('repository', '?')))}`: {entry.get('reason', '')}"
        for entry in rejections
    )
    lines += [
        "",
        "## Discovery diagnostics",
        "",
        f"- Queries: {len(report['discovery'].get('queries', []))}",
        f"- Search errors: {len(report['discovery'].get('errors', []))}",
    ]
    cache = report["discovery"].get("cache", {})
    if cache:
        lines.append(
            f"- Cache hits: {cache.get('disk_cache_hits', 0)} disk / {cache.get('memory_cache_hits', 0)} memory; "
            f"network requests: {cache.get('requests', 0)}; retries: {cache.get('retries', 0)}."
        )
    errors = Counter(
        (entry.get("operation", "search"), entry.get("reason", "unknown"))
        for entry in report["discovery"].get("errors", [])
    )
    for (operation, reason), count in errors.most_common(10):
        lines.append(f"- {operation}: {reason} ({count} occurrence(s)).")
    lines.extend(f"- {item}" for item in report["profile"].get("warnings", []))
    lines.extend(f"- {item}" for item in report["limitations"])
    return "\n".join(lines) + "\n"


def output_report(report, *, output=None, format="markdown", root=None):
    text = json_text(report) if format == "json" else markdown_report(report)
    if output is None:
        print(text, end="")
        return
    path = Path(output).expanduser().resolve()
    if root is not None and path.is_relative_to(root.resolve()):
        raise ValueError("proposal output must be outside the target repository")
    atomic_write(path, text)
