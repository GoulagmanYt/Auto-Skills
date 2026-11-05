"""Bounded manifest ownership for independently versioned repository workspaces.

Each dependency manifest establishes a package boundary. This covers packages
expanded by npm/Cargo workspace globs as well as mixed-language services which
are not declared in the root package manager. Configuration belongs to the
nearest enclosing boundary; a parent never receives a child's dependencies.
"""

from copy import deepcopy
from pathlib import Path

from .adapters import is_package_manifest
from .profile import BASE_SLOTS, manifest_paths, profile_repo

RUNTIMES = {
    "node",
    "python",
    "rust",
    "go",
    "java",
    "dotnet",
    "dart",
    "swift",
    "elixir",
    "r",
    "julia",
}
SCOPED_BASE_SLOTS = {"unit-testing", "build"}


def _roots(root, paths):
    from .repo_config import configured_scopes

    scopes = {".", *configured_scopes(root)}
    for path in paths:
        if not is_package_manifest(path.name):
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            continue
        scopes.add(path.parent.relative_to(root).as_posix())
    return sorted(scopes, key=lambda scope: (scope != ".", scope))


def workspace_roots(root: Path):
    """Return actual package directories, never phantom glob matches or source files."""
    root = Path(root).resolve()
    return _roots(root, list(manifest_paths(root)))


def _owner(root, path, scopes):
    relative = path.parent.relative_to(root)
    for scope in sorted(scopes, key=lambda value: len(Path(value).parts), reverse=True):
        if scope != "." and relative.is_relative_to(Path(scope)):
            return scope
    return "."


def _inherit_runtimes(profile, parent, parent_scope):
    for technology in sorted(RUNTIMES):
        relevant = {technology}
        if technology == "node":
            relevant.update({"javascript", "typescript"})
        if not relevant.intersection(profile.technologies):
            continue
        if profile.technologies.get(technology) not in (None, "detected", "unresolved"):
            continue
        value = parent.technologies.get(technology)
        if value in (None, "detected", "unresolved", "multiple"):
            continue
        sources = [
            {**deepcopy(source), "inherited_from": source.get("inherited_from", parent_scope)}
            for source in parent.technology_sources.get(technology, [])
            if source.get("kind") in {"runtime", "declaration"}
        ]
        if not sources:
            continue
        profile.technologies[technology] = value
        profile.technology_sources.setdefault(technology, []).extend(sources)
        resolved = [source["version"] for source in sources if source.get("kind") == "runtime"]
        if resolved:
            profile.resolved_versions[technology] = sorted(set(resolved))
        for slot in ("build", "ci-cd"):
            profile.slot_technologies[slot] = sorted(
                set(profile.slot_technologies.get(slot, [])) | {technology}
            )


def workspace_profiles(root: Path, root_profile=None):
    """Return isolated profiles keyed by ``.`` or a POSIX repository-relative scope.

    Source paths in each profile are local to its package. Inherited runtime
    declarations additionally record their parent scope. No dependency versions
    or lockfile resolutions are copied between sibling workspaces.
    """
    from .repo_config import apply_configuration

    root = Path(root).resolve()
    diagnostics = []
    paths = list(manifest_paths(root, diagnostics=diagnostics))
    scopes = _roots(root, paths)
    if scopes == ["."] and root_profile is not None:
        return apply_configuration(root, {".": deepcopy(root_profile)})
    owned = {scope: [] for scope in scopes}
    for path in paths:
        owned[_owner(root, path, scopes)].append(path)
    profiles = {scope: profile_repo(root / scope, paths=owned[scope]) for scope in scopes}
    profiles["."].diagnostics.extend(diagnostics)
    for scope in sorted(scopes, key=lambda value: (len(Path(value).parts), value)):
        if scope == ".":
            continue
        parents = [
            candidate
            for candidate in scopes
            if candidate != scope
            and (candidate == "." or Path(scope).is_relative_to(Path(candidate)))
        ]
        # A Rust package between a root Node pin and a JS package must not
        # inherit Node itself, or prevent the JS package from finding that pin.
        for parent in sorted(parents, key=lambda value: len(Path(value).parts), reverse=True):
            _inherit_runtimes(profiles[scope], profiles[parent], parent)
    return apply_configuration(root, profiles)


def selection_profiles(root: Path, root_profile=None):
    """Keep repository-wide guidance once, with versioned package skills below it."""
    profiles = workspace_profiles(root, root_profile)
    for scope, profile in profiles.items():
        if scope == ".":
            continue
        profile.slots = [
            slot
            for slot in profile.slots
            if slot not in BASE_SLOTS
            or slot in SCOPED_BASE_SLOTS
            or slot in profile.manual_configuration.get("slots", [])
        ]
        profile.slot_technologies = {
            slot: technologies
            for slot, technologies in profile.slot_technologies.items()
            if slot in profile.slots
        }
    return profiles


def profile_for_scope(root: Path, scope=".", root_profile=None):
    """Resolve an existing scope without accepting paths outside the repository."""
    profiles = workspace_profiles(root, root_profile)
    if scope not in profiles:
        raise ValueError(f"unknown workspace scope: {scope}")
    return profiles[scope]
