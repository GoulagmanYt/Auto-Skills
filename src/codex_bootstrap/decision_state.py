"""Versioned, optional session state. Cached data never grants new capabilities."""

import json
import re
from pathlib import Path
from typing import TypedDict


class RepositoryIdentity(TypedDict):
    checkout: str
    git_directory: str
    head: str
    revision: str


def read_decision(path: Path):
    """Return a validated v1 record, or None for unavailable/unsupported state."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 500_000:
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or type(value.get("schema_version")) is not int
            or value["schema_version"] != 1
        ):
            return None
        if not isinstance(value.get("decision_id"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", value["decision_id"]
        ):
            return None
        identity = value.get("repository")
        if not isinstance(identity, dict) or not all(
            isinstance(identity.get(k), str) for k in RepositoryIdentity.__annotations__
        ):
            return None
        for key, limit in (
            ("scopes", 64),
            ("files", 64),
            ("required_capabilities", 256),
            ("uncertainties", 256),
        ):
            entries = value.get(key)
            if (
                not isinstance(entries, list)
                or len(entries) > limit
                or not all(isinstance(e, str) for e in entries)
            ):
                return None
        selected = value.get("selected")
        if not isinstance(selected, list) or len(selected) > 20:
            return None
        keys = (
            "key",
            "scope",
            "slot",
            "name",
            "path",
            "discovery_path",
            "sha256",
            "source",
            "reason",
        )
        if not all(
            isinstance(e, dict) and all(isinstance(e.get(k), str) for k in keys) for e in selected
        ):
            return None
        metrics = value.get("metrics")
        if (
            not isinstance(metrics, dict)
            or type(metrics.get("selected_count")) is not int
            or metrics["selected_count"] != len(selected)
        ):
            return None
        if not isinstance(value.get("states"), dict) or not isinstance(
            value.get("created_at"), str
        ):
            return None
        return value
    except (OSError, ValueError, TypeError):
        return None
