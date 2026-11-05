"""Read-only explanation of the locked catalog for a workspace launch."""

import math
import re

from .config import active_scope, enabled_skills, integration_settings
from .fs import confined
from .profile import BASE_SLOTS


def inspect_context(root, *, cwd=None, integration_mode=None):
    from .bootstrap import verify_lock

    root = root.resolve()
    current = (cwd or root).resolve()
    if not current.is_relative_to(root):
        raise ValueError("workspace is outside repository")
    lock = verify_lock(root)
    scope = active_scope(root, lock, current)
    active_paths = {e["discovery_path"] for e in enabled_skills(lock, scope)}
    active, excluded = [], []
    characters = 0
    for entry in lock["skills"]:
        selected = entry["discovery_path"] in active_paths
        local = entry.get("scope", ".") == scope
        record = {
            key: entry.get(key)
            for key in (
                "scope",
                "slot",
                "name",
                "source",
                "repository",
                "commit",
                "compatibility",
                "discovery_path",
                "technologies",
            )
        }
        key = (
            entry["slot"]
            if entry.get("scope", ".") == "."
            else entry["scope"] + "::" + entry["slot"]
        )
        record["technology_evidence"] = (
            lock.get("slot_inputs", {}).get(key, {}).get("declarations", {})
        )
        if selected:
            record["reason"] = (
                "active workspace guide"
                if local
                else "portable common guide inherited from repository root"
            )
            text = confined(root, entry["discovery_path"]).read_text(encoding="utf-8")
            match = re.search(r"(?m)^description:\s*(.+)$", text)
            characters += (
                len(entry["name"])
                + len(match[1] if match else "")
                + len(entry["discovery_path"])
                + 16
            )
            active.append(record)
        else:
            if entry.get("scope", ".") != ".":
                reason = "different workspace"
            elif entry["slot"] not in BASE_SLOTS:
                reason = "root specialization is not inherited"
            elif entry.get("technologies") or entry.get("compatibility"):
                reason = "common slot has technology-specific constraints"
            else:
                reason = "overridden by active workspace guide"
            record["reason"] = reason
            excluded.append(record)
    integrations = integration_settings(root, integration_mode)
    policy = lock.get("policy", {})
    scoped_policy = policy.get("scope_policies", {}).get(scope, policy)
    return {
        "workspace": scope,
        "repository_kind": scoped_policy.get("repository_kind", "unknown"),
        "classification_reason": scoped_policy.get(
            "classification_reason", "legacy lock; refresh for current classification"
        ),
        "unrecognized_evidence": scoped_policy.get("unrecognized_evidence", []),
        "inspection_diagnostics": scoped_policy.get("inspection_diagnostics", []),
        "integration_policy": integrations,
        "active": active,
        "excluded": excluded,
        "catalog_cost": {
            "estimated_tokens": math.ceil(characters / 4),
            "method": "catalog characters / 4; excludes native wrappers, instructions, tools and external integrations",
            "billing_measurement": False,
        },
        "limitations": [
            "This is an estimate of locked catalog metadata, not total session usage.",
            "External guides may add context in coexist mode.",
            "Bundled coverage is a fallback; it does not establish an eligible external guide exists.",
        ],
        "missing_external_coverage": [e["slot"] for e in active if e["source"] == "bundled"],
    }


def markdown_context(report):
    lines = [
        "# Workspace context",
        "",
        f"Workspace: `{report['workspace']}`. Integration mode: `{report['integration_policy']['mode']}`.",
        f"Repository kind: `{report['repository_kind']}` — {report['classification_reason']}.",
        f"Estimated locked catalog: {report['catalog_cost']['estimated_tokens']} tokens (characters / 4; not billing).",
        "",
        "| Status | Workspace | Guide | Source | Reason |",
        "|---|---|---|---|---|",
    ]
    for status, key in (("active", "active"), ("excluded", "excluded")):
        for entry in report[key]:
            cells = [
                status,
                entry.get("scope") or ".",
                entry.get("name") or entry["slot"],
                entry.get("repository") or entry.get("source") or "unknown",
                entry["reason"],
            ]
            lines.append(
                "| "
                + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in cells)
                + " |"
            )
    lines += ["", *report["limitations"]]
    if report["unrecognized_evidence"]:
        lines += ["", "Unrecognized filename evidence (no source content read):"]
        lines += [
            "- `" + path.replace("`", "\\`").replace("\n", " ") + "`"
            for path in report["unrecognized_evidence"]
        ]
    if report["inspection_diagnostics"]:
        lines += [
            "",
            "Inspection is incomplete; consult inspection_diagnostics in JSON for excluded paths and scan limits.",
        ]
    return "\n".join(lines) + "\n"
