"""Passive, bounded tool evidence. Never retain tool arguments or tool output."""

import ast
import hashlib
import json
import os
import re
import shlex
import time
from itertools import islice
from pathlib import Path
from stat import S_ISLNK

from .fs import atomic_write, json_text
from .github import default_cache_dir


def observation_directory(root, session):
    def digest(value):
        return hashlib.sha256(str(value).encode()).hexdigest()

    return default_cache_dir() / "dashboard-v1" / digest(root.resolve()) / digest(session)


def outcome(response):
    if not isinstance(response, dict):
        return "unverified"
    if response.get("isError") is True or response.get("error"):
        return "error"
    for key in ("exit_code", "exitCode"):
        if type(response.get(key)) is int:
            return "ok" if response[key] == 0 else "error"
    if response.get("isError") is False or "content" in response:
        return "ok"
    return "unverified"


def literal_reads(command, depth=0):
    """Recognize literal reads through our wrapper; never evaluate shell or Python."""
    if depth > 3 or not isinstance(command, str):
        return []
    lexer = shlex.shlex(command, posix=False, punctuation_chars=";")
    lexer.whitespace_split, lexer.commenters = True, ""
    tokens = list(lexer)
    if ";" in tokens:
        paths, group = [], []
        for token in [*tokens, ";"]:
            if token == ";":
                paths.extend(literal_reads(" ".join(group), depth + 1))
                group = []
            else:
                group.append(token)
        return paths

    def unquote(value):
        return (
            value[1:-1] if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'" else value
        )

    if tokens[:1] == ["&"]:
        tokens = tokens[1:]

    if (
        len(tokens) > 2
        and unquote(tokens[0]).replace("\\", "/").rsplit("/", 1)[-1].lower()
        in {"token-run", "token-run.cmd", "token-run.ps1"}
        and tokens[1] == "--"
    ):
        tokens = tokens[2:]
    if not tokens:
        return []
    program = unquote(tokens[0]).replace("\\", "/").rsplit("/", 1)[-1].lower().removesuffix(".exe")
    if program in {"powershell", "pwsh"}:
        for index, token in enumerate(tokens[1:], 1):
            if token.lower() in {"-command", "-c"}:
                return literal_reads(unquote(" ".join(tokens[index + 1 :])), depth + 1)
    if program in {"get-content", "cat", "type"}:
        return [unquote(token.rstrip(",")) for token in tokens[1:] if not token.startswith("-")]
    if program in {"python", "python3"} and "-c" in tokens:
        code = unquote(" ".join(tokens[tokens.index("-c") + 1 :]))
        paths = []
        for node in ast.walk(ast.parse(code)):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"read_text", "read_bytes"}
            ):
                constructor = node.func.value
                if (
                    isinstance(constructor, ast.Call)
                    and isinstance(constructor.func, ast.Name)
                    and constructor.func.id == "Path"
                    and constructor.args
                    and isinstance(constructor.args[0], ast.Constant)
                    and isinstance(constructor.args[0].value, str)
                ):
                    paths.append(constructor.args[0].value)
        return paths
    return []


def record_tool_event(root, event):
    if event.get("hook_event_name") != "PostToolUse":
        return
    session = os.environ.get("CODEX_BOOTSTRAP_OBSERVATION_SESSION")
    if not session:
        return
    tool = event.get("tool_name", "")
    if not isinstance(tool, str) or len(tool) > 256:
        return
    response = event.get("tool_response")
    result = outcome(response)
    require_contents = False
    reads = []
    args = event.get("tool_input")
    if result != "error" and isinstance(args, dict):
        paths = []
        if tool.lower().split(".")[-1] in {"read", "read_file", "read_text_file"}:
            paths = [args.get("path", args.get("file_path", ""))]
        elif tool in {"Bash", "exec_command", "shell"}:
            command = args.get("command", args.get("cmd", ""))
            if isinstance(command, str):
                require_contents = bool(
                    re.search(r"(?:^|[\s/\\])python(?:3|\.exe)?\s", command, re.I)
                )
                try:
                    paths = literal_reads(command)
                except (ValueError, SyntaxError):
                    paths = []
        lock_path = root / ".codex/skills-lock.json"
        if paths and lock_path.is_file() and lock_path.stat().st_size <= 4_000_000:
            lock = json.loads(lock_path.read_text(encoding="utf-8"))
            cwd = Path(event.get("cwd", str(root)))
            requested = {(cwd / p).resolve() for p in paths if isinstance(p, str) and p}
            for skill in lock.get("skills", []):
                path = skill.get("path", "")
                target = (root / path).resolve()
                aliases = [target]
                if isinstance(skill.get("discovery_path"), str):
                    discovery = (root / skill["discovery_path"]).resolve()
                    if discovery.is_relative_to(root.resolve()):
                        aliases.append(discovery)
                if target.is_relative_to(root.resolve()) and any(
                    alias in requested for alias in aliases
                ):
                    verified_read = result == "ok" and not require_contents
                    returned_text = response if isinstance(response, str) else ""
                    if isinstance(response, dict):
                        returned_text = "\n".join(
                            response[k]
                            for k in ("stdout", "output", "content")
                            if isinstance(response.get(k), str)
                        )
                    if (
                        not verified_read
                        and returned_text
                        and target.is_file()
                        and target.stat().st_size < 100_000
                    ):
                        content = target.read_text(encoding="utf-8").strip().replace("\r\n", "\n")
                        verified_read = len(content) >= 16 and content in returned_text.replace(
                            "\r\n", "\n"
                        )
                    if verified_read:
                        reads.append(path)
    match = re.fullmatch(r"(?:[A-Za-z_]+\.)?mcp__([A-Za-z0-9_-]+)__(.+)", tool)
    if not reads and not match:
        return
    call = event.get("tool_use_id")
    if not isinstance(call, str) or not call:
        return
    directory = observation_directory(root, session)
    record = {
        "version": 1,
        "time": time.time_ns(),
        "reads": reads,
        "server": match[1] if match else "",
        "outcome": result,
    }
    atomic_write(
        directory / (hashlib.sha256(call.encode()).hexdigest() + ".json"), json_text(record)
    )
    # Keep disk use bounded for long sessions. Each file is independently replaceable.
    files = list(islice(directory.glob("*.json"), 1100))
    if len(files) > 1000:
        files.sort(key=lambda p: p.stat().st_mtime_ns)
        for old in files[:-1000]:
            old.unlink(missing_ok=True)


def read_observations(root, session, *, cache=None):
    records = []
    seen = set()
    for path in islice(observation_directory(root, session).glob("*.json"), 1000):
        try:
            seen.add(path)
            stat = path.lstat()
            if S_ISLNK(stat.st_mode) or stat.st_size > 32_000:
                continue
            stamp = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_ino, stat.st_size)
            previous = cache.get(path) if cache is not None else None
            value = (
                previous[1]
                if previous and previous[0] == stamp
                else json.loads(path.read_text(encoding="utf-8"))
            )
            if (
                not isinstance(value, dict)
                or value.get("version") != 1
                or type(value.get("time")) is not int
                or not isinstance(value.get("reads"), list)
                or not all(isinstance(p, str) for p in value["reads"])
                or not isinstance(value.get("server"), str)
                or not isinstance(value.get("outcome"), str)
                or value.get("outcome") not in {"ok", "error", "unverified"}
            ):
                continue
            if cache is not None:
                cache[path] = (stamp, value)
            records.append(value)
        except (OSError, ValueError, RecursionError):
            continue
    if cache is not None:
        for stale in set(cache) - seen:
            del cache[stale]
    return sorted(records, key=lambda v: v.get("time", 0))
