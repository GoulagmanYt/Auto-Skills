"""Repository-sized skill baselines and explicit, reviewable tool plans."""

from copy import deepcopy

from .profile import BASE_SLOTS
from .repo_inspection import classify_repository

PRESETS = ("auto", "documentation", "minimal", "complete")
TOKEN_SLOTS = [slot for slot in BASE_SLOTS if slot.startswith("token-")]
DOC_TECH = {"markdown", "mkdocs", "sphinx", "docusaurus", "mdbook"}
DOC_SUPPORT = {
    "python",
    "javascript",
    "typescript",
    "node",
    "npm",
    "pnpm",
    "yarn",
    "bun",
    "react",
    "react-dom",
    "mkdocs-material",
    "mike",
    "pymdown-extensions",
    "pyyaml",
    "sphinx-rtd-theme",
    "furo",
    "myst-parser",
    "sphinx-autobuild",
    "clsx",
    "prism-react-renderer",
    "eslint",
    "prettier",
    "github-actions",
    "gitlab-ci",
}


def policy_for(root, profile, preset="auto"):
    if preset not in PRESETS:
        raise ValueError("unknown bootstrap preset")
    technologies = set(profile.technologies)
    generator = bool(
        technologies & DOC_TECH
        or any(tech.startswith("@docusaurus/") for tech in technologies)
        or any((root / name).is_file() for name in ("mkdocs.yml", "mkdocs.yaml", "book.toml"))
    )
    allowed = DOC_TECH | {"github-actions", "gitlab-ci"}
    if generator:
        allowed |= DOC_SUPPORT | {tech for tech in technologies if tech.startswith("@docusaurus/")}
    classification = classify_repository(
        root,
        profile,
        documentary_technologies=allowed,
        documentation_generator=generator,
    )
    kind = classification["kind"]
    effective = (
        {"application": "complete", "documentation": "documentation", "unknown": "unknown"}[kind]
        if preset == "auto"
        else preset
    )
    return {
        "preset": preset,
        "effective": effective,
        "version": 2,
        "repository_kind": kind,
        "classification_reason": classification["reason"],
        "unrecognized_evidence": classification["unrecognized_evidence"],
        "inspection_incomplete": classification["inspection_incomplete"],
        "inspection_diagnostics": classification["diagnostics"],
        "technology_hints": classification["technology_hints"],
    }


def adapt_profile(profile, policy):
    result = deepcopy(profile)
    if policy["effective"] == "unknown":
        explicit = set(getattr(profile, "manual_configuration", {}).get("slots", []))
        result.slots = [slot for slot in result.slots if slot in BASE_SLOTS or slot in explicit]
        return result
    if policy["effective"] == "documentation":
        result.slots = [slot for slot in TOKEN_SLOTS + ["documentation"] if slot in result.slots]
        return result
    elif policy["effective"] == "minimal":
        baseline = TOKEN_SLOTS + ["unit-testing", "security", "documentation"]
    else:
        baseline = BASE_SLOTS
    result.slots = [slot for slot in result.slots if slot not in BASE_SLOTS or slot in baseline]
    return result


def tool_plan(profile, policy):
    names = ["token-run", "repo-map"]
    scoped = policy.get("scope_policies", {}).values()
    application = policy["effective"] not in {"documentation", "unknown"} or any(
        p["effective"] not in {"documentation", "unknown"} for p in scoped
    )
    if application:
        names.append("rtk")
    technologies = set(profile.technologies) | set(policy.get("technology_hints", []))
    for scoped in policy.get("scope_policies", {}).values():
        technologies.update(scoped.get("technology_hints", []))
    if policy["preset"] == "complete" or (
        application
        and {
            "javascript",
            "typescript",
            "node",
            "react",
            "vue",
            "nextjs",
            "next",
            "svelte",
        }.intersection(technologies)
    ):
        names.append("repomix")
    reasons = {
        "token-run": "bounded terminal output with a recovery log",
        "repo-map": "bounded file map and Python AST navigation without a runtime download",
        "rtk": "compress Git, build and test output for application development",
        "repomix": "compressed repository export for JavaScript/TypeScript workspaces; explicit complete preset also includes it",
    }
    return [{"name": name, "reason": reasons[name]} for name in names]
