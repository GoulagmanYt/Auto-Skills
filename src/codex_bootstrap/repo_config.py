"""Validated, inert repository declarations with explicit manual provenance."""

import re
import tomllib
from copy import deepcopy
from pathlib import Path, PurePosixPath

from .adapters import LANGUAGES as ADAPTER_LANGUAGES
from .adapters import TECH_SLOTS as ADAPTER_TECH_SLOTS
from .fs import confined
from .profile import BASE_SLOTS, DOMAIN_SLOTS, PYTHON_DOMAIN_SLOTS, SKIP, TECH_SLOTS

CONFIG_NAME = "auto-skills.toml"
CONFIG_LIMIT = 64 * 1024
KINDS = {"auto", "application", "documentation", "unknown"}
LANGUAGES = ADAPTER_LANGUAGES
EXTRA_SLOTS = ADAPTER_TECH_SLOTS


def _error(reason):
    # Never include untrusted settings values, which could contain credentials.
    return ValueError(f"{CONFIG_NAME}: {reason}")


def _keys(value, allowed, label):
    if not isinstance(value, dict) or set(value) - allowed:
        raise _error(f"invalid {label} fields")


def _scope(root, value):
    if not isinstance(value, str) or not 1 <= len(value) <= 200:
        raise _error("workspace path must be a bounded repository-relative string")
    path = PurePosixPath(value)
    if (
        "\\" in value
        or ":" in value
        or path.is_absolute()
        or value != path.as_posix()
        or any(part in {".", ".."} for part in path.parts)
    ):
        raise _error("unsafe workspace path")
    if any(part.casefold() in {name.casefold() for name in SKIP} for part in path.parts):
        raise _error("workspace path uses a generated, vendor, or reserved directory")
    try:
        target = confined(root, value)
    except ValueError:
        raise _error("workspace path redirects or escapes the repository") from None
    if not target.is_dir():
        raise _error("workspace path must name an existing directory")
    cursor = target
    while cursor != root:
        if (cursor / ".git").exists():
            raise _error("workspace path crosses a nested repository or submodule")
        cursor = cursor.parent
    return value


def _supported_slots():
    from .catalog import RULES

    return (
        set(BASE_SLOTS)
        | set(RULES)
        | set(TECH_SLOTS.values())
        | {slot for slots in DOMAIN_SLOTS.values() for slot in slots}
        | {slot for slots in PYTHON_DOMAIN_SLOTS.values() for slot in slots}
        | {f"language-{name}" for name in LANGUAGES}
        | set(EXTRA_SLOTS.values())
        | {"e2e-testing", "static-analysis"}
    )


def read_configuration(root: Path) -> dict:
    """Return normalized v1 settings, failing closed before callers write anything.

    Missing configuration is equivalent to empty settings. Unknown keys, unsafe
    scopes and unsupported schema versions are errors, never executable inputs.
    """
    root = Path(root).resolve()
    try:
        path = confined(root, CONFIG_NAME)
    except ValueError:
        raise _error("configuration must be an ordinary repository file") from None
    empty = {"schema_version": 1, "repository": {}, "workspaces": []}
    if not path.exists():
        return empty
    if not path.is_file() or path.stat().st_size > CONFIG_LIMIT:
        raise _error("configuration must be a file of at most 65536 bytes")
    try:
        with path.open("rb") as stream:
            payload = stream.read(CONFIG_LIMIT + 1)
        if len(payload) > CONFIG_LIMIT:
            raise _error("configuration exceeds 65536 bytes")
        data = tomllib.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        raise _error("configuration is unreadable or invalid TOML") from None
    _keys(data, {"schema_version", "repository", "workspaces"}, "top-level")
    version = data.get("schema_version", 1)
    if type(version) is not int or version != 1:
        raise _error("unsupported schema_version; expected 1")
    repository = data.get("repository", {})
    _keys(repository, {"kind"}, "repository")
    if "kind" in repository and (
        not isinstance(repository["kind"], str) or repository["kind"] not in KINDS
    ):
        raise _error("repository kind must be auto, application, documentation, or unknown")
    workspaces = data.get("workspaces", [])
    if not isinstance(workspaces, list) or len(workspaces) > 256:
        raise _error("workspaces must be an array of at most 256 tables")
    seen = set()
    for entry in workspaces:
        _keys(entry, {"path", "kind", "technologies", "slots"}, "workspace")
        scope = _scope(root, entry.get("path"))
        if scope.casefold() in seen:
            raise _error("duplicate workspace path")
        seen.add(scope.casefold())
        if "kind" in entry and (not isinstance(entry["kind"], str) or entry["kind"] not in KINDS):
            raise _error("workspace kind must be auto, application, documentation, or unknown")
        technologies = entry.get("technologies", {})
        if not isinstance(technologies, dict) or len(technologies) > 128:
            raise _error("technologies must be a table of at most 128 entries")
        for name, constraint in technologies.items():
            if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name):
                raise _error(
                    "technology names must be lowercase identifiers, without paths or URLs"
                )
            if (
                not isinstance(constraint, str)
                or not 1 <= len(constraint) <= 100
                or not re.fullmatch(r"[0-9vVxX*<>=!^~.,| +\-]+", constraint)
                or not re.search(r"[0-9xX*]", constraint)
            ):
                raise _error("technology versions must be bounded numeric version constraints")
        slots = entry.get("slots", [])
        if (
            not isinstance(slots, list)
            or len(slots) > 128
            or any(not isinstance(slot, str) or slot not in _supported_slots() for slot in slots)
            or len(slots) != len(set(slots))
        ):
            raise _error("slots must be distinct supported role names")
    return {"schema_version": 1, "repository": repository, "workspaces": workspaces}


def configuration_for_scope(root: Path, scope=".") -> dict:
    """Return explicit settings for one scope; repository kind applies to root."""
    settings = read_configuration(root)
    result = dict(settings["repository"]) if scope == "." else {}
    result.update(next((item for item in settings["workspaces"] if item["path"] == scope), {}))
    return result


def configured_scopes(root: Path) -> list[str]:
    return [entry["path"] for entry in read_configuration(root)["workspaces"]]


def apply_configuration(root: Path, profiles) -> dict:
    """Overlay manual intent, preserving all observed declarations separately."""
    settings = read_configuration(root)
    result = deepcopy(profiles)
    entries = {entry["path"]: entry for entry in settings["workspaces"]}
    if settings["repository"]:
        entries["."] = {**settings["repository"], **entries.get(".", {})}
    for scope, entry in entries.items():
        if scope not in result:
            raise _error("configured workspace is missing from the bounded profile inventory")
        profile = result[scope]
        profile.manual_configuration = deepcopy(entry)
        if "kind" in entry:
            profile.repository_kind = entry["kind"]
            profile.kind_source = {"kind": "manual", "path": CONFIG_NAME, "scope": scope}
        for technology, version in entry.get("technologies", {}).items():
            sources = profile.technology_sources.setdefault(technology, [])
            observed = [source for source in sources if source.get("kind") != "manual"]
            if any(
                source.get("version") not in {None, "detected", "unresolved", version}
                for source in observed
            ):
                profile.warnings.append(
                    f"{CONFIG_NAME}: manual {technology} override differs from observed declarations; "
                    "declaration conflict retained for review (manual intent controls selection)."
                )
            profile.technology_sources[technology] = [
                {
                    "kind": "manual",
                    "path": CONFIG_NAME,
                    "scope": scope,
                    "version": version,
                    "constraint": version,
                },
                *observed,
            ]
            profile.technologies[technology] = version
            profile.components.append(
                {
                    "name": technology,
                    "technology": technology,
                    "role": "manual",
                    "source": CONFIG_NAME,
                    "version": version,
                    "kind": "manual",
                    "scope": scope,
                }
            )
            slots = []
            if technology in LANGUAGES:
                slots.append(f"language-{technology}")
            if technology in TECH_SLOTS:
                slots.append(TECH_SLOTS[technology])
            if technology in EXTRA_SLOTS:
                slots.append(EXTRA_SLOTS[technology])
            slots.extend(DOMAIN_SLOTS.get(technology, ()))
            if not slots and technology not in {"node", "npm", "pnpm", "yarn", "bun"}:
                profile.warnings.append(
                    f"{CONFIG_NAME}: manual {technology} has no specialized capability mapping; "
                    "version intent is recorded, specialized support is unknown."
                )
            for slot in slots:
                profile.slots.append(slot)
                profile.slot_technologies[slot] = sorted(
                    set(profile.slot_technologies.get(slot, [])) | {technology}
                )
            for slot in (
                "architecture",
                "security",
                "performance",
                "refactoring",
                "documentation",
                "unit-testing",
                "build",
                "ci-cd",
            ):
                profile.slot_technologies[slot] = sorted(
                    set(profile.slot_technologies.get(slot, [])) | {technology}
                )
        profile.slots = list(dict.fromkeys([*profile.slots, *entry.get("slots", [])]))
    return result
