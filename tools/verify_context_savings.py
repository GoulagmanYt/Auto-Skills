"""Measure native Codex startup context on temporary manifest-only repository copies.

Run with: uv run --with tiktoken python tools/verify_context_savings.py
No inference request is made. Public skills may be fetched, but downloadable token
tools are kept offline to isolate the skill-selection experiment.
"""

# ruff: noqa: E402
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "src"))

from codex_bootstrap import __version__
from codex_bootstrap.bootstrap import bootstrap
from codex_bootstrap.config import active_scope, enabled_skills, launch_profile
from codex_bootstrap.fs import json_text
from codex_bootstrap.github import GitHub, default_cache_dir
from codex_bootstrap.profile import BASE_SLOTS, manifest_fingerprint, manifest_paths, profile_repo
from codex_bootstrap.proposal import markdown_report as proposal_markdown_report
from codex_bootstrap.proposal import selection_plan

PROMPT = "Inspect only the manifest for this project."
GENERATED = (".codex", ".agents", "AGENTS.md", ".codexignore")


def git_status(root):
    return subprocess.check_output(
        ["git", "-C", str(root), "status", "--porcelain=v1"],
        text=True,
        encoding="utf-8",
    )


def normalized(text, root):
    for path, replacement in ((root, "<REPO>"),):
        values = {str(path), path.as_posix(), json.dumps(str(path))[1:-1]}
        for value in sorted(values, key=len, reverse=True):
            text = text.replace(value, replacement)
    return text


def prompt_metrics(codex, args, root, encoding):
    process = subprocess.run(
        [codex, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    if process.returncode:
        raise RuntimeError(f"Codex debug prompt-input exited {process.returncode}")
    data = json.loads(process.stdout)
    if not isinstance(data, list):
        raise ValueError("unrecognized native prompt-input shape; cannot compare safely")
    texts, catalogs, names, paths, tools = [], [], [], [], []
    for message in data:
        for part in message.get("content", []):
            if isinstance(part.get("text"), str):
                text = normalized(part["text"], root)
                texts.append(text)
                sections = re.findall(r"<skills_instructions>.*?</skills_instructions>", text, re.S)
                catalogs.extend(sections)
                for section in sections:
                    roots = dict(re.findall(r"^- `([^`]+)` = `([^`]+)`$", section, re.M))
                    for line in section.splitlines():
                        if re.match(r"^- .+?:\s", line) and "(file:" in line:
                            names.append(line[2:].split(": ", 1)[0])
                            match = re.search(r"\(file: (.+)\)$", line)
                            if not match:
                                raise ValueError("unrecognized native skill path")
                            path = match[1].replace("\\", "/")
                            alias, separator, suffix = path.partition("/")
                            if alias in roots and separator:
                                path = roots[alias].replace("\\", "/").rstrip("/") + "/" + suffix
                            paths.append(path)
        if message.get("type") == "additional_tools":
            tools.extend(message.get("tools", []))

    def count(text):
        return len(encoding.encode(text, disallowed_special=()))

    text_tokens = sum(count(text) for text in texts)
    catalog_tokens = sum(count(text) for text in catalogs)
    tool_tokens = (
        count(normalized(json.dumps(tools, ensure_ascii=False, sort_keys=True), root))
        if tools
        else 0
    )
    return {
        "text_tokens": text_tokens,
        "skill_catalog_tokens": catalog_tokens,
        "other_text_tokens": text_tokens - catalog_tokens,
        "additional_tool_schema_tokens": tool_tokens,
        "exposed_context_tokens": text_tokens + tool_tokens,
        "visible_skills": len(names),
        "unique_visible_skills": len(set(names)),
        "duplicate_skill_entries": len(names) - len(set(names)),
        "skill_names": names,
        "skill_paths": paths,
        "additional_tools": len(tools),
        "native_stderr_lines": len(process.stderr.splitlines()),
    }


def clone_manifests(source, destination):
    subprocess.run(["git", "init", "-q", str(destination)], check=True, capture_output=True)
    paths = list(manifest_paths(source))
    paths += [source / "README.md"] if (source / "README.md").is_file() else []
    # Preserve existing repository instructions/configuration in the control.
    for current in (source, *(path.parent for path in paths)):
        for relative in ("AGENTS.md", "AGENTS.override.md", ".codex/config.toml"):
            path = current / relative
            if path.is_file() and path not in paths:
                paths.append(path)
    for path in paths:
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError("redirected audit input")
        target = destination / path.relative_to(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)


def delta(before, after):
    return {
        key: {
            "before": before[key],
            "after": after[key],
            "saved": before[key] - after[key],
            "reduction_percent": round(100 * (before[key] - after[key]) / before[key], 2)
            if before[key]
            else None,
        }
        for key in ("exposed_context_tokens", "skill_catalog_tokens", "visible_skills")
    }


def markdown_report(record, output):
    lines = [
        "# Proposals and context measurement: Piano-LED-Visualizer / RTP-OSC-Midi-tool",
        "",
        "The original repositories were not modified. Skills were installed in temporary copies of the manifests, with external resources pinned. No model calls were made.",
        "",
        "## Proposed skills",
        "",
        "Shared root baseline: " + ", ".join(f"`{slot}`" for slot in BASE_SLOTS) + ".",
        "",
        "| Project / workspace | Bundled skills | External GitHub skills |",
        "|---|---|---|",
    ]
    tool_notes = []
    for project in record["projects"]:
        name = Path(project["source"]).name
        proposal = json.loads((output / name.lower() / "proposal.json").read_text(encoding="utf-8"))
        for scope in proposal["workspaces"]:
            entries = [e for e in proposal["selected"] if e["scope"] == scope]
            internal = [
                e["name"]
                for e in entries
                if e["source"] == "bundled" and (scope != "." or e["slot"] not in BASE_SLOTS)
            ]
            local = ("Shared baseline + " if scope == "." else "") + ", ".join(
                f"`{s}`" for s in internal
            )
            external = [f"[{e['name']}]({e['url']})" for e in entries if e["source"] == "github"]
            lines.append(
                f"| {name} / `{scope}` | {local} | {', '.join(external) or 'None selected'} |"
            )
        tools = ", ".join(f"`{tool['name']}`" for tool in proposal["tool_plan"])
        tool_notes += [
            f"**{name}**: {project['selected_skills']} skills across {len(proposal['workspaces'])} workspaces; proposed tools: {tools}.",
            "",
        ]
    lines += ["", *tool_notes]
    lines += [
        "## Before / after at the root",
        "",
        "Estimates from the `o200k_base` tokenizer, using the text and additional schemas exposed by the real `codex debug prompt-input`. This is neither a billing statement nor a measurement of a complete session.",
        "",
        "| Project | Usual Codex | Installed without wrapper | Wrapper active | Reduction with wrapper | Skill catalog before → after |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for project in record["projects"]:
        scope = project["scope_measurements"]["."]
        before, plain, after = (
            scope["before"],
            scope["installed_without_wrapper"],
            scope["with_wrapper"],
        )
        saved = scope["delta"]["exposed_context_tokens"]["reduction_percent"]
        lines.append(
            f"| {Path(project['source']).name} | {before['exposed_context_tokens']} | {plain['exposed_context_tokens']} | {after['exposed_context_tokens']} | {saved} % | {before['skill_catalog_tokens']} → {after['skill_catalog_tokens']} |"
        )
    lines += [
        "",
        "The total number of installed skills differs from the number loaded at the root. Workspace selection limits activation. Full SKILL.md bodies are normally read on demand; the table measures their catalog and initial instructions.",
        "",
        "## Measurements by workspace",
        "",
        "| Project / workspace | Usual context | With wrapper | Unique visible skills | Duplicate entries | Specialties inherited from root |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for project in record["projects"]:
        for name, scope in project["scope_measurements"].items():
            after = scope["with_wrapper"]
            inherited = ", ".join(f"`{s}`" for s in scope["inherited_root_specialty_slots"])
            lines.append(
                f"| {Path(project['source']).name} / `{name}` | {scope['before']['exposed_context_tokens']} | {after['exposed_context_tokens']} | {after['unique_visible_skills']} | {after['duplicate_skill_entries']} | {inherited or '—'} |"
            )
    lines += [
        "",
        "## What the verification establishes",
        "",
        "- Initial context changes are measured per environment and workspace in the tables above. They do not predict savings for a complete task.",
        "- Guide bodies are kept in `.codex/skills` and `.agents/skills` for integrity, but the wrapper activates only the `.agents` copy. Each native catalog path was compared against the lock: this verification rejects duplicates, missing paths and unexpected paths.",
        "- Child workspaces receive their own guides and only the portable common guides from the root. Root specialties are not inherited. Inheritance columns are derived from the paths actually exposed by Codex.",
        "- Piano detects `mido`, `python-rtmidi`, `rpi.gpio` and `rpi-ws281x`, but the current catalog assigns no dedicated Python MIDI or LED/Raspberry Pi skill to them. This gap remains visible.",
        "- Downloadable binary tools remained offline to isolate skill measurement. No RTK/Repomix compression, cache or full-task token savings are claimed.",
        "",
        "## Reproduction",
        "",
        "```sh",
        "uv run --no-project --with tiktoken python tools/verify_context_savings.py",
        "```",
        "",
        "Structured results: `context-comparison.json` and JSON/Markdown proposals per project. GitHub searches are bounded; the absence of an external winner does not imply that no relevant guide exists.",
    ]
    return "\n".join(lines) + "\n"


def audit(source, output, github, encoding, codex):
    source = source.resolve()
    original_status, fingerprints = git_status(source), manifest_fingerprint(source)
    original_generated = {name: (source / name).exists() for name in GENERATED}
    profile = profile_repo(source)
    selected, proposal = selection_plan(profile, root=source, github=github)
    summary = {
        "source": str(source),
        "input_manifest_hashes": fingerprints,
        "selected_skills": len(selected),
        "external_skills": [entry for entry in proposal["selected"] if entry["source"] == "github"],
        "scope_measurements": {},
        "original_root_baseline": prompt_metrics(
            codex, ["-C", str(source), "debug", "prompt-input", PROMPT], source, encoding
        ),
    }
    with tempfile.TemporaryDirectory(prefix="auto-skills-context-") as temporary:
        root = Path(temporary).resolve()
        clone_manifests(source, root)
        baselines = {}
        for scope in proposal["workspaces"]:
            cwd = root / scope
            cwd.mkdir(parents=True, exist_ok=True)
            args = ["-C", str(cwd), "debug", "prompt-input", PROMPT]
            baselines[scope] = prompt_metrics(codex, args, root, encoding)
        # Install exactly the live selection, including pinned external resources.
        # Binary downloads do not contribute to this startup-catalog measurement.
        installed_proposal = deepcopy(proposal)
        with patch(
            "codex_bootstrap.bootstrap.selection_plan", return_value=(selected, installed_proposal)
        ):
            lock = bootstrap(root, offline=True)
        summary["installed_tools"] = [
            {"name": t["name"], "status": t["status"]} for t in lock["tools"]
        ]
        for scope in proposal["workspaces"]:
            cwd = root / scope
            args = ["-C", str(cwd), "debug", "prompt-input", PROMPT]
            plain = prompt_metrics(codex, args, root, encoding)
            with launch_profile(root, lock, args, cwd) as launch_args:
                wrapped = prompt_metrics(codex, launch_args, root, encoding)
            active = active_scope(root, lock, cwd)
            visible = set(wrapped["skill_paths"])
            expected = {"<REPO>/" + e["discovery_path"] for e in enabled_skills(lock, active)}
            validation = {
                "missing_paths": sorted(expected - visible),
                "unexpected_paths": sorted(visible - expected),
                "duplicate_paths": len(wrapped["skill_paths"]) - len(visible),
            }
            inherited = [
                e["slot"]
                for e in lock["skills"]
                if active != "."
                and e.get("scope", ".") == "."
                and e["slot"] not in BASE_SLOTS
                and any("<REPO>/" + e[key] in visible for key in ("path", "discovery_path"))
            ]
            summary["scope_measurements"][scope] = {
                "before": baselines[scope],
                "installed_without_wrapper": plain,
                "with_wrapper": wrapped,
                "delta": delta(baselines[scope], wrapped),
                "inherited_root_specialty_slots": inherited,
                "catalog_validation": validation,
            }
            if any(validation.values()) or inherited:
                raise AssertionError(f"native catalog isolation failed for {scope}: {validation}")
        # Exact class instances/names/paths are taken from the native prompt, not
        # inferred from the number of installed SKILL.md files.
    assert original_status == git_status(source), "target working tree status changed"
    assert fingerprints == manifest_fingerprint(source), "target manifests changed"
    assert original_generated == {name: (source / name).exists() for name in GENERATED}, (
        "target configuration changed"
    )
    summary["target_unchanged"] = True
    summary["baseline_copy_matches_original"] = all(
        summary["original_root_baseline"][key] == summary["scope_measurements"]["."]["before"][key]
        for key in ("exposed_context_tokens", "skill_catalog_tokens", "visible_skills")
    )
    output.mkdir(parents=True, exist_ok=True)
    proposal.update({"target": str(source), "installed": False})
    (output / "proposal.json").write_text(json_text(proposal), encoding="utf-8")
    (output / "proposal.md").write_text(proposal_markdown_report(proposal), encoding="utf-8")
    (output / "context-comparison.json").write_text(json_text(summary), encoding="utf-8")
    return summary


def main(argv=None):
    import tiktoken

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", type=Path)
    parser.add_argument(
        "--output", type=Path, default=default_cache_dir().parent / "private-measurements"
    )
    options = parser.parse_args(argv)
    repos = options.repo or [
        WORKSPACE.parent / "Piano-LED-Visualizer",
        WORKSPACE.parent / "RTP-OSC-Midi-tool",
    ]
    output = options.output.resolve()
    for repo in repos:
        if output.is_relative_to(repo.resolve()):
            raise ValueError("audit output must be outside target repositories")
    codex = shutil.which("codex")
    if not codex:
        raise RuntimeError("Codex CLI is required for native prompt measurement")
    encoding = tiktoken.get_encoding("o200k_base")
    github = GitHub(max_requests=240, timeout=180, max_retries=1)
    results = []
    for repo in repos:
        result = audit(repo, output / repo.name.lower(), github, encoding, codex)
        results.append(result)
        print(
            json.dumps(
                {
                    "project": repo.name,
                    "selected": result["selected_skills"],
                    "root_delta": result["scope_measurements"]["."]["delta"],
                    "target_unchanged": result["target_unchanged"],
                }
            ),
            flush=True,
        )
    record = {
        "created_at": datetime.now(UTC).isoformat(),
        "tokenizer": "o200k_base",
        "tokenizer_version": tiktoken.__version__,
        "bootstrap_version": __version__,
        "native_codex": codex,
        "native_codex_version": subprocess.check_output(
            [codex, "--version"], text=True, encoding="utf-8", timeout=15
        ).strip(),
        "method": "same temporary manifest-only Git repository before/after; same prompt and real user Codex home; model calls: 0",
        "limitations": [
            "Tokenization estimates the exposed debug prompt text and additional tool schemas, not server-side billing or full model request usage.",
            "Skill catalog metadata is measured; complete SKILL.md bodies are normally read later on demand.",
            "The wrapper also disables global plugins/MCP, changes policy text and reasoning effort; total-context change cannot be attributed only to skill selection.",
            "Binary token tools stayed offline; their compression savings are not measured here.",
            "No task execution or cache hit measurement: no claim of reduced total session tokens or cost.",
        ],
        "github_stats": github.stats,
        "projects": results,
    }
    (output / "context-comparison.json").write_text(json_text(record), encoding="utf-8")
    (output / "summary.md").write_text(markdown_report(record, output), encoding="utf-8")


if __name__ == "__main__":
    main()
