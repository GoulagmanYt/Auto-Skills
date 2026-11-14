"""Trust only manager-owned hooks using hashes reported by the installed Codex.

No global hook-trust bypass is used. User/plugin/project hooks keep their native
trust state. A cached capability probe is invalidated by executable or manager
changes and makes no inference request.
"""

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import threading
from pathlib import Path

from .config import toml_value
from .fs import atomic_write, json_text
from .github import default_cache_dir


def trusted_overrides(expected, response):
    states = {}
    events = {name[0].lower() + name[1:]: command for name, command in expected.items()}
    for item in response.get("data", []):
        for hook in item.get("hooks", []):
            if (
                hook.get("source") != "sessionFlags"
                or hook.get("handlerType") != "command"
                or hook.get("command") != events.get(hook.get("eventName"))
            ):
                continue
            if not re.fullmatch(r"sha256:[0-9a-f]{64}", hook.get("currentHash", "")):
                raise ValueError("invalid native hook content hash")
            states[hook["key"]] = {"trusted_hash": hook["currentHash"]}
    return ["-c", "hooks.state=" + toml_value(states)] if states else []


def list_hooks(real_command, root, overrides, *, timeout=15):
    process = subprocess.Popen(
        [*real_command, *overrides, "app-server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=root,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    timer = threading.Timer(timeout, process.kill)
    timer.daemon = True
    timer.start()
    try:
        requests = [
            {
                "id": 1,
                "method": "initialize",
                "params": {"clientInfo": {"name": "auto-skills-hook-verifier", "version": "1"}},
            },
            {"method": "initialized"},
            {"id": 2, "method": "hooks/list", "params": {"cwds": [str(root)]}},
        ]
        for request in requests:
            process.stdin.write(json.dumps(request) + "\n")
            process.stdin.flush()
            if "id" not in request:
                continue
            for _ in range(128):
                line = process.stdout.readline(1_000_001)
                if not line or len(line) > 1_000_000:
                    raise RuntimeError("native hook probe ended without a bounded response")
                response = json.loads(line)
                if response.get("id") == request["id"]:
                    if "error" in response:
                        raise ValueError("native hook probe rejected the request")
                    if request["id"] == 2:
                        return response["result"]
                    break
            else:
                raise ValueError("native hook probe event budget exceeded")
    finally:
        timer.cancel()
        process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        process.stdout.close()
    raise ValueError("native hook probe returned no hooks")


def hook_overrides(real_command, root):
    Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).mkdir(
        parents=True, exist_ok=True
    )
    command = " ".join(map(shlex.quote, [sys.executable, "-I", "-m", "codex_bootstrap.hooks"]))
    if os.name == "nt":
        command = "& '" + sys.executable.replace("'", "''") + "' -I -m codex_bootstrap.hooks"
    expected = {event: command for event in ("SessionStart", "UserPromptSubmit", "PostToolUse")}
    definitions = {
        event: [
            {
                "hooks": [
                    {
                        "type": "command",
                        "command": cmd,
                        "timeout": 5 if event == "PostToolUse" else 180,
                        "additionalContextLimit": 8000,
                        "statusMessage": "Observing tool usage"
                        if event == "PostToolUse"
                        else "Preparing task skills",
                    }
                ]
            }
        ]
        for event, cmd in expected.items()
    }
    args = [
        value
        for event, definition in definitions.items()
        for value in ("-c", "hooks." + event + "=" + toml_value(definition))
    ]
    executable = Path(real_command[0]).resolve()
    signature = hashlib.sha256(
        json_text(
            {
                "command": real_command,
                "mtime": executable.stat().st_mtime_ns,
                "size": executable.stat().st_size,
                "hooks": definitions,
            }
        ).encode()
    ).hexdigest()
    path = default_cache_dir() / "native-hooks-v1" / (signature + ".json")
    try:
        trust = None
        if path.is_file() and not path.is_symlink() and path.stat().st_size < 32_000:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if cached.get("signature") == signature:
                trust = trusted_overrides(expected, cached["response"])
        if not trust:
            response = list_hooks(real_command, root, args)
            trust = trusted_overrides(expected, response)
            if not trust:
                raise ValueError("installed Codex did not expose both manager hooks")
            minimal = {
                "data": [
                    {
                        "hooks": [
                            {
                                k: h[k]
                                for k in (
                                    "source",
                                    "handlerType",
                                    "eventName",
                                    "command",
                                    "key",
                                    "currentHash",
                                )
                            }
                            for row in response.get("data", [])
                            for h in row.get("hooks", [])
                            if h.get("source") == "sessionFlags"
                            and h.get("handlerType") == "command"
                            and h.get("command") in expected.values()
                        ]
                    }
                ]
            }
            atomic_write(path, json_text({"signature": signature, "response": minimal}))
        return args + trust
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
        print(
            "Auto-Skills: native lifecycle hooks unavailable; launch selection remains active. Use the task manager when the task changes.",
            file=sys.stderr,
        )
        return []
