"""Repository dashboard: installation, observed consultation and tool outcomes."""

import hashlib
import json
import os
import subprocess
import time
import unicodedata
from pathlib import Path

from .config import integration_settings
from .observations import read_observations


def inventory_json(command, *, env=None, cwd=None, cancel=None):
    """Bound metadata processes and reap them when the panel's owner exits."""
    with subprocess.Popen(
        command,
        env=env,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    ) as process:
        deadline = time.monotonic() + 15
        try:
            while True:
                if (cancel is not None and cancel.is_set()) or time.monotonic() >= deadline:
                    raise TimeoutError("native inventory cancelled or timed out")
                try:
                    output, _ = process.communicate(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if process.returncode or len(output) > 2_000_000:
                raise ValueError("native inventory unavailable")
            return json.loads(output)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=2)


def native_integrations(command, *, env=None, cwd=None, cancel=None):
    """Read native inventories, without starting servers or invoking plugin tools."""
    result = {"plugins": [], "mcp": [], "errors": []}
    for kind, args in (
        ("plugins", ["plugin", "list", "--json"]),
        ("mcp", ["mcp", "list", "--json"]),
    ):
        if cancel is not None and cancel.is_set():
            break
        try:
            data = inventory_json([*command, *args], env=env, cwd=cwd, cancel=cancel)
            if kind == "plugins" and not isinstance(data, dict):
                raise ValueError("unsupported native plugin inventory")
            items = data.get("installed", []) if kind == "plugins" else data
            if not isinstance(items, list):
                raise ValueError("unsupported native inventory")
            for item in items[:1000]:
                if not isinstance(item, dict):
                    continue
                if not isinstance(item.get("name"), str) or not isinstance(
                    item.get("pluginId", ""), str
                ):
                    result["errors"].append(kind + ": identifiant invalide")
                    continue
                if kind == "plugins":
                    name = item.get("name", "")
                    # A matching plugin name alone is not proof of MCP ownership.
                    servers = []
                    source = item.get("source", {})
                    if isinstance(source, dict) and isinstance(source.get("path"), str):
                        try:
                            manifest = Path(source["path"]) / ".mcp.json"
                            if manifest.is_file() and manifest.stat().st_size <= 100_000:
                                payload = json.loads(manifest.read_text(encoding="utf-8"))
                                declarations = (
                                    payload.get("mcpServers", payload)
                                    if isinstance(payload, dict)
                                    else None
                                )
                                if not isinstance(declarations, dict):
                                    raise ValueError("invalid MCP manifest")
                                servers.extend(k for k in declarations if isinstance(k, str))
                        except (OSError, ValueError, RecursionError):
                            result["errors"].append("plugins: manifeste MCP invalide")
                    result[kind].append(
                        {
                            "id": item.get("pluginId", name),
                            "name": name,
                            "version": item.get("version", ""),
                            "enabled": item.get("enabled") is True,
                            "servers": sorted(set(servers)),
                        }
                    )
                else:
                    result[kind].append(
                        {"name": item.get("name", ""), "enabled": item.get("enabled") is True}
                    )
        except (OSError, ValueError, TypeError, RecursionError, subprocess.SubprocessError):
            result["errors"].append(kind + ": inventaire natif indisponible")
    return result


def snapshot(root, *, session="", integrations=None, observation_cache=None):
    root = root.resolve()
    lock_path = root / ".codex/skills-lock.json"
    if lock_path.stat().st_size > 4_000_000:
        raise ValueError("skill lock exceeds dashboard budget")
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except RecursionError as exc:
        raise ValueError("invalid dashboard skill lock") from exc
    if (
        not isinstance(lock, dict)
        or not isinstance(lock.get("skills"), list)
        or not all(isinstance(s, dict) for s in lock["skills"])
        or not isinstance(lock.get("files", {}), dict)
    ):
        raise ValueError("invalid dashboard skill lock")
    if any(not isinstance(s.get("path"), str) for s in lock["skills"]):
        raise ValueError("invalid dashboard skill paths")
    policy = integration_settings(root)
    events = read_observations(root, session, cache=observation_cache)
    reads, servers = {}, {}
    for event in events:
        for path in event.get("reads", []):
            if isinstance(path, str):
                reads[path] = reads.get(path, 0) + 1
        if event.get("server"):
            previous = servers.get(event["server"], {"calls": 0})
            servers[event["server"]] = {
                "calls": previous["calls"] + 1,
                "health": event.get("outcome", "unverified"),
            }
    skills = []
    for skill in lock.get("skills", []):
        path = skill.get("path", "")
        target = (root / path).resolve()
        integrity = "missing"
        expected = lock.get("files", {}).get(path)
        if target.is_relative_to(root) and target.is_file() and target.stat().st_size <= 1_000_000:
            integrity = "unverified"
            if isinstance(expected, str):
                integrity = (
                    "ok"
                    if hashlib.sha256(target.read_bytes()).hexdigest() == expected
                    else "changed"
                )
        skills.append(
            {
                "name": skill.get("name", skill.get("slot", "")),
                "slot": skill.get("slot", ""),
                "scope": skill.get("scope", "."),
                "reads": reads.get(path, 0),
                "integrity": integrity,
            }
        )
    integrations = integrations or {"plugins": [], "mcp": [], "errors": []}
    result = {
        "repository": str(root),
        "mode": policy["mode"],
        "session": bool(session),
        "skills": skills,
        "plugins": [],
        "mcp": [],
        "errors": integrations.get("errors", []),
    }
    for kind, allow in (("plugins", "keep_plugins"), ("mcp", "keep_mcp")):
        for item in integrations.get(kind, []):
            name = item.get("id", item["name"])
            available = item.get("enabled", False) and (
                policy["mode"] == "coexist" or name in policy[allow]
            )
            names = item.get("servers", [item["name"]])
            evidence = [e for e in events if e.get("server") in names]
            health = evidence[-1].get("outcome", "unverified") if evidence else "unverified"
            result[kind].append(
                {
                    **item,
                    "available": available,
                    "calls": len(evidence),
                    "health": health if available else "disabled",
                }
            )
    known = {item["name"] for item in result["mcp"]}
    for name, evidence in servers.items():
        if name not in known:
            result["mcp"].append({"name": name, "available": None, **evidence})
    return result


def clean(value):
    return "".join(c if not unicodedata.category(c).startswith("C") else " " for c in str(value))


def clipped(value, width):
    result, cells = [], 0
    text = clean(value)
    for index, character in enumerate(text):
        size = (
            0
            if unicodedata.category(character) in {"Mn", "Me"}
            else 2
            if unicodedata.east_asian_width(character) in {"W", "F"}
            else 1
        )
        # VS16 and keycap marks promote otherwise narrow bases to emoji width.
        if size and index + 1 < len(text) and text[index + 1] in {"\ufe0f", "\u20e3"}:
            size = 2
        if cells + size > width:
            break
        result.append(character)
        cells += size
    return "".join(result)


def render(report, *, tab=0, width=100, height=30, offset=0):
    status = {
        "ok": "OK (observe)",
        "error": "ERREUR observee",
        "disabled": "Desactive",
        "unverified": "Non verifie",
        "missing": "Fichier absent",
        "changed": "Fichier modifie",
    }
    tabs = ["1 Skills", "2 Plugins", "3 MCP"]
    navigation = "  ".join(
        "[" + label + (" *]" if index == tab else "]") for index, label in enumerate(tabs)
    )
    lines = [
        "AUTO-SKILLS  |  F9 / Esc : retour Codex",
        navigation + "  |  R : actualiser",
        "Depot : " + clean(report["repository"]),
        "Mode : " + report["mode"] + "  |  Preuves de cette session uniquement",
        "",
    ]
    kind = ("skills", "plugins", "mcp")[tab]
    rows = []
    if kind == "skills":
        rows.append("Installes / lectures observees (application non certifiee)")
        for item in report[kind]:
            rows.append(
                f"{item['reads']:>3} lecture(s) | {status[item['integrity']]} | {item['slot']} [{item['scope']}] | {item['name']}"
            )
    else:
        rows.append("Disponibilite / derniers appels observes")
        for item in report[kind]:
            rows.append(
                f"{item['name']} | {item['calls']} appel(s) | {status.get(item['health'], 'Non verifie')}"
            )
        if not report[kind]:
            rows.append("Aucun element connu. R : lire les inventaires natifs.")
    rows.extend(report.get("errors", []))
    lines.extend(rows[max(0, offset) : max(0, offset) + max(0, height - 7)])
    lines.extend(["", "Haut/Bas : defiler | Actif ne signifie pas fonctionnel"])
    return "\n".join(clipped(line, max(1, width)) for line in lines[: max(1, height)])
