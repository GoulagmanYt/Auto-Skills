"""Reconcile only project trust explicitly written into a disposable Codex profile."""

import copy
import json
import os
import re
import shutil
import tempfile
import tomllib
from pathlib import Path

from .fs import atomic_write, confined
from .runtime_loader import file_mutex


def levels(config):
    return {
        key: project["trust_level"]
        for key, project in config.get("projects", {}).items()
        if isinstance(project, dict) and project.get("trust_level") in ("trusted", "untrusted")
    }


def _read(path):
    try:
        with path.open("rb") as stream:
            data = stream.read(2_000_001)
    except FileNotFoundError:
        return b""
    if len(data) > 2_000_000:
        raise ValueError("Codex config exceeds read budget")
    return data


# Use source offsets to preserve comments, spelling, CRLF and unrelated values.
# tomllib validates both documents. Tokens only locate the edited field.
_TOKEN = re.compile(
    r'''"""(?:\\[\s\S]|"(?!"")|[^"\\])*"{3,5}'''
    + r"""|'''(?:'(?!'')|[^'])*'{3,5}"""
    + r"""|"(?:\\.|[^"\\])*"|'[^']*'|#[^\r\n]*|[ \t]+|\r?\n|[\[\]{},.=]|[^\s\[\]{},.=#'"]+"""
)


def _edit(text, key, level, *, empty_project=False):
    tokens = [m for m in _TOKEN.finditer(text) if not m[0].startswith(("#", " ", "\t"))]
    end = len(tokens)
    target = ("projects", key, "trust_level")
    newline = "\r\n" if "\r\n" in text else "\n"
    # (depth, insertion offset, inline table, comma needed)
    insertion = (0, 0, False, False)
    replacement = None

    def token(i):
        return tokens[i][0] if i < end else ""

    def key_path(i):
        parts = []
        while i < end:
            name = token(i)
            if name.startswith(("'", '"')):
                name = tomllib.loads("k=" + name)["k"]
            parts.append(name)
            i += 1
            if token(i) != ".":
                break
            i += 1
        return tuple(parts), i

    def value_end(i, inline):
        depth = 0
        while i < end:
            s = token(i)
            if depth == 0 and (s in ("\n", "\r\n") or (inline and s in (",", "}"))):
                break
            depth += int(s in ("[", "{")) - int(s in ("]", "}"))
            i += 1
        return i

    def assignment(i, prefix, inline=False):
        nonlocal insertion, replacement
        name, eq = key_path(i)
        if token(eq) != "=":
            raise ValueError("could not locate a TOML assignment")
        field = prefix + name
        start = eq + 1
        stop = value_end(start, inline)
        if field == target:
            if level is not None:
                replacement = (tokens[start].start(), tokens[stop - 1].end(), json.dumps(level))
            elif empty_project and len(name) > 1:
                # A lone dotted assignment implicitly created its project table.
                replacement = (tokens[eq - 2].start(), tokens[stop - 1].end(), " = {}")
            else:
                first, last = i, stop - 1
                if inline and token(stop) == ",":
                    last = stop
                elif inline and i and token(i - 1) == ",":
                    first = i - 1
                replacement = (tokens[first].start(), tokens[last].end(), "")
        elif target[: len(field)] == field and token(start) == "{":
            if len(field) >= insertion[0]:
                insertion = (len(field), tokens[start].end(), True, token(start + 1) != "}")
            j = start + 1
            while j < stop and token(j) != "}":
                if token(j) in (",", "\n", "\r\n"):
                    j += 1
                else:
                    j = assignment(j, field, True)
        return stop

    i, section = 0, ()
    while i < end:
        if token(i) in ("\n", "\r\n"):
            i += 1
        elif token(i) == "[":
            array = token(i + 1) == "["
            section, i = key_path(i + (2 if array else 1))
            i += 2 if array else 1
            if array:
                section += (None,)
            if target[: len(section)] == section and len(section) >= insertion[0]:
                offset = tokens[i].end() if i < end else len(text)
                insertion = (len(section), offset, False, False)
        else:
            i = assignment(i, section)

    if replacement is not None:
        start, stop, value = replacement
        return text[:start] + value + text[stop:]
    if level is None:
        return text
    depth, offset, inline, comma = insertion
    # Append a new project at EOF when possible to preserve the user's layout.
    if not depth and key not in tomllib.loads(text).get("projects", {}):
        suffix = "[projects." + json.dumps(key, ensure_ascii=False) + "]"
        return (
            text
            + (newline if text and not text.endswith("\n") else "")
            + suffix
            + newline
            + "trust_level = "
            + json.dumps(level)
            + newline
        )
    name = ".".join(json.dumps(part, ensure_ascii=False) for part in target[depth:])
    entry = name + " = " + json.dumps(level)
    if inline:
        entry += ", " if comma else ""
    else:
        if offset and text[offset - 1] != "\n":
            entry = newline + entry
        entry += newline
    return text[:offset] + entry + text[offset:]


def _publish(path, original, data, existed):
    """Keep existing mode and reject intervening external edits before replace."""
    fd, tmp = tempfile.mkstemp(prefix=".auto-skills-trust-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink() or path.exists() != existed or _read(path) != original:
            raise RuntimeError("native configuration changed during trust reconciliation")
        if not existed:
            # Atomic create without replacing a file concurrently created by Codex.
            if os.name == "nt":
                os.rename(tmp, path)
            else:
                os.link(tmp, path)
        elif os.name == "nt":
            # ReplaceFileW preserves the original DACL. Do not ignore merge errors.
            import ctypes
            from ctypes import wintypes

            replace = ctypes.WinDLL("kernel32", use_last_error=True).ReplaceFileW
            replace.argtypes = [wintypes.LPCWSTR] * 3 + [
                wintypes.DWORD,
                wintypes.LPVOID,
                wintypes.LPVOID,
            ]
            replace.restype = wintypes.BOOL
            if not replace(str(path), tmp, None, 0, None, None):
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            if path.stat().st_uid != os.geteuid():
                raise ValueError("refusing to change native configuration ownership")
            if path.stat().st_gid != os.stat(tmp).st_gid:
                os.chown(tmp, -1, path.stat().st_gid)
            shutil.copystat(path, tmp)
            os.utime(tmp, None)
            os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def _document(text):
    # Preserve the distinction between strings, numbers and TOML nan on reparse.
    return tomllib.loads(text, parse_float=lambda literal: ("float", literal))


def _apply(home, destination, changes):
    path = confined(home, destination)
    existed = path.exists()
    original = _read(path)
    text = original.decode("utf-8")
    current = _document(text)
    expected = copy.deepcopy(current)
    current_levels = levels(current)
    base_levels = {}
    if destination != "config.toml":
        base_levels = levels(tomllib.loads(_read(confined(home, "config.toml")).decode("utf-8")))
    for key, (before, after, inherited) in changes.items():
        if current_levels.get(key) != before or before == after:
            continue
        if before is None and base_levels.get(key) != inherited:
            continue
        if after is None:
            del expected["projects"][key]["trust_level"]
        else:
            expected.setdefault("projects", {}).setdefault(key, {})["trust_level"] = after
        text = _edit(text, key, after, empty_project=not expected["projects"][key])
    if expected == current:
        return
    if _document(text) != expected:
        raise ValueError("could not preserve unrelated Codex configuration")
    _publish(path, original, text.encode("utf-8"), existed)


_STATE = "auto-skills-trust"


def start_session(home, path, destination, initial, durable, inherited):
    directory = confined(home, _STATE)
    directory.mkdir(mode=0o700, exist_ok=True)
    receipt = confined(directory, path.stem + ".json")
    atomic_write(
        receipt,
        json.dumps(
            {
                "version": 1,
                "session_profile": path.name,
                "destination": destination.name,
                "initial": initial,
                "durable": durable,
                "inherited": inherited,
            }
        ),
    )
    return receipt


def reconcile(home, receipt, path, destination, initial, final, durable, inherited):
    changes = {
        key: [durable.get(key), final.get(key), inherited.get(key)]
        for key in sorted(initial.keys() | final.keys())
        if initial.get(key) != final.get(key)
    }
    if changes:
        # No automatic replay. A crash after replace is indistinguishable from
        # a later native revocation that restored the old bytes or removed the file.
        atomic_write(
            receipt,
            json.dumps(
                {
                    "version": 1,
                    "destination": destination.name,
                    "changes": changes,
                }
            ),
        )
    path.unlink()
    if changes:
        try:
            with file_mutex(confined(home, _STATE + "/merge.lock")):
                _apply(home, destination.name, changes)
        except (OSError, ValueError, RuntimeError) as exc:
            raise RuntimeError(f"project trust requires manual review: {receipt}") from exc
    receipt.unlink()
