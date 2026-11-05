"""Bounded filename-only evidence for conservative repository classification."""

import os
from itertools import islice
from pathlib import Path

from .profile import SKIP

DOCUMENT_SUFFIXES = {
    ".md",
    ".rst",
    ".txt",
    ".adoc",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".ico",
    ".pdf",
}
METADATA = {
    ".gitignore",
    ".gitattributes",
    ".gitmodules",
    ".codexignore",
    ".editorconfig",
    ".pre-commit-config.yaml",
    ".readthedocs.yaml",
    ".readthedocs.yml",
    "LICENSE",
    "LICENSE.md",
    "LICENSE.txt",
    "NOTICE",
    "COPYING",
    "CODEOWNERS",
    "auto-skills.toml",
}
IGNORED = SKIP | {
    ".serena",
    ".ruff_cache",
    ".pytest_cache",
    ".benchmark-work",
    "dist-alpha",
    "dist-ci",
    ".cache",
    ".tox",
    ".mypy_cache",
}


def inspect_repository(root, *, max_entries=10000, max_depth=8):
    """List bounded relative names; never open implementation files."""
    root = Path(root).resolve()
    files, diagnostics = [], []
    count = 0
    stack = [(root, 0)]
    while stack:
        directory, depth = stack.pop()
        try:
            with os.scandir(directory) as stream:
                entries = sorted(
                    islice(stream, max_entries - count + 1), key=lambda entry: entry.name
                )
        except OSError:
            diagnostics.append(
                {"code": "unreadable_directory", "path": directory.relative_to(root).as_posix()}
            )
            continue
        for entry in entries:
            count += 1
            if count > max_entries:
                diagnostics.append(
                    {"code": "entry_limit", "path": directory.relative_to(root).as_posix()}
                )
                return {"files": files, "diagnostics": diagnostics, "incomplete": True}
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            try:
                if entry.is_symlink():
                    diagnostics.append({"code": "excluded_symlink", "path": relative})
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if entry.name in IGNORED:
                        continue
                    if path.resolve() != path.absolute():
                        diagnostics.append(
                            {"code": "excluded_redirected_directory", "path": relative}
                        )
                        continue
                    if (path / ".git").exists():
                        diagnostics.append({"code": "excluded_git_boundary", "path": relative})
                    elif depth >= max_depth:
                        diagnostics.append({"code": "depth_limit", "path": relative})
                    else:
                        stack.append((path, depth + 1))
                elif entry.is_file(follow_symlinks=False):
                    files.append(relative)
            except (OSError, RuntimeError):
                diagnostics.append({"code": "unreadable_entry", "path": relative})
    return {"files": files, "diagnostics": diagnostics, "incomplete": bool(diagnostics)}


def classify_repository(
    root, profile, *, documentary_technologies=(), documentation_generator=False
):
    inspection = inspect_repository(root)
    known_manifests = set(profile.manifests)
    unknown = []
    for relative in inspection["files"]:
        path = Path(relative)
        if relative in known_manifests or path.name in METADATA or path.name == ".git":
            continue
        if documentation_generator and path.name in {
            "mkdocs.yml",
            "mkdocs.yaml",
            "book.toml",
            "docusaurus.config.js",
            "docusaurus.config.ts",
            "sidebars.js",
            "sidebars.ts",
        }:
            continue
        if path.suffix.lower() in DOCUMENT_SUFFIXES:
            continue
        if relative.startswith(".github/"):
            continue
        if documentation_generator and path.parts[0] in {"docs", "src", "static", "assets"}:
            continue
        unknown.append(relative)
    kind, reason = (
        "unknown",
        "no supported application manifest or verified documentation-only file set",
    )
    explicit = getattr(profile, "repository_kind", "auto")
    manual = bool(getattr(profile, "kind_source", None))
    configured = None
    config_path = Path(root) / "auto-skills.toml"
    if config_path.exists() or config_path.is_symlink():
        from .repo_config import read_configuration

        configured = read_configuration(root)
        repository_kind = configured.get("repository", {}).get("kind", "auto")
        if not manual and repository_kind != "auto":
            explicit, manual = repository_kind, True
    if manual and explicit in {"application", "documentation", "unknown"}:
        kind, reason = explicit, "explicit user repository classification"
    elif set(profile.technologies) - set(documentary_technologies):
        kind, reason = "application", "recognized application technology evidence"
    elif configured and any(w.get("technologies") for w in configured.get("workspaces", [])):
        kind, reason = "application", "explicit workspace technology declarations"
    elif unknown or inspection["incomplete"] or profile.warnings:
        reason = "unrecognized files, incomplete inspection or manifest diagnostics require review"
    elif inspection["files"] and any(
        Path(p).suffix.lower() in {".md", ".rst", ".adoc"}
        and Path(p).name.upper() not in {"AGENTS.MD", "CLAUDE.MD", "GEMINI.MD"}
        for p in inspection["files"]
    ):
        kind, reason = (
            "documentation",
            "only documentation, known documentation manifests and metadata observed",
        )
    return {
        "kind": kind,
        "reason": reason,
        "unrecognized_evidence": unknown[:25],
        "unrecognized_count": len(unknown),
        "inspection_incomplete": inspection["incomplete"],
        "diagnostics": inspection["diagnostics"][:100],
        "technology_hints": sorted(
            set(profile.technologies)
            | {
                tech
                for workspace in (configured or {}).get("workspaces", [])
                for tech in workspace.get("technologies", {})
            }
        ),
    }
