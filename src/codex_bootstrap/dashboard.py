"""Repository dashboard: installation, observed consultation and tool outcomes."""

import hashlib
import json
import os
import subprocess
import unicodedata
from pathlib import Path

from .config import integration_settings
from .observations import read_observations


def native_integrations(command, *, env=None, cwd=None):
    """Read native inventories, without starting servers or invoking plugin tools."""
    result = {"plugins": [], "mcp": [], "errors": []}
    for kind, args in (
        ("plugins", ["plugin", "list", "--json"]),
        ("mcp", ["mcp", "list", "--json"]),
    ):
        try:
            process = subprocess.run(
                [*command, *args],
                env=env,
                cwd=cwd,
                capture_output=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if process.returncode or len(process.stdout) > 2_000_000:
                raise ValueError("native inventory unavailable")
            data = json.loads(process.stdout)
            items = data.get("installed", []) if kind == "plugins" else data
            if not isinstance(items, list):
                raise ValueError("unsupported native inventory")
            for item in items[:1000]:
                if not isinstance(item, dict):
                    continue
                if kind == "plugins":
                    name = item.get("name", "")
                    # A matching plugin name alone is not proof of MCP ownership.
                    servers = []
                    source = item.get("source", {})
                    if isinstance(source, dict) and isinstance(source.get("path"), str):
                        manifest = Path(source["path"]) / ".mcp.json"
                        if manifest.is_file() and manifest.stat().st_size <= 100_000:
                            payload = json.loads(manifest.read_text(encoding="utf-8"))
                            declarations = payload.get("mcpServers", payload)
                            if isinstance(declarations, dict):
                                servers.extend(k for k in declarations if isinstance(k, str))
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
        except (OSError, ValueError, TypeError, subprocess.SubprocessError):
            result["errors"].append(kind + ": inventaire natif indisponible")
    return result


def snapshot(root, *, session="", integrations=None):
    root = root.resolve()
    lock_path = root / ".codex/skills-lock.json"
    if lock_path.stat().st_size > 4_000_000:
        raise ValueError("skill lock exceeds dashboard budget")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    policy = integration_settings(root)
    events = read_observations(root, session)
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
    return "\n".join(clean(line)[: max(1, width)] for line in lines[: max(1, height)])
