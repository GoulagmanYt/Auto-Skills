"""User-global permissions; project and remote instructions cannot widen them."""

import os
import tomllib
from pathlib import Path


def automatic_policy():
    home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    path = home / "auto-skills.toml"
    if not path.exists():
        return {}
    if path.stat().st_size > 32_000:
        raise ValueError("automatic source policy exceeds budget")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    policy = data.get("automatic", {})
    if not isinstance(policy, dict):
        raise ValueError("invalid automatic policy")
    return policy


def optional_tools():
    tools = automatic_policy().get("optional_tools", [])
    if not isinstance(tools, list) or any(not isinstance(t, str) or t != "repomix" for t in tools):
        raise ValueError("invalid automatic optional_tools; supported: repomix")
    return set(tools)
