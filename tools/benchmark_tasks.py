"""Complete synthetic tasks with native Codex usage and independent validation.

Dry runs never invoke inference or install competitors. Live runs are explicit.
Runtime dependencies are Python's standard library and the selected local tools.
"""

# ruff: noqa: E402
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time
from collections import Counter
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
EXAMPLES = WORKSPACE / "fixtures/benchmark"
COMPETITORS = WORKSPACE / "benchmarks/competitors.json"
sys.path.insert(0, str(WORKSPACE / "src"))

from codex_bootstrap import __version__
from codex_bootstrap.bootstrap import bootstrap
from codex_bootstrap.config import (
    config_layers,
    external_skills,
    launch_profile,
    read_toml,
    toml_value,
)
from codex_bootstrap.fs import atomic_write

POLICY = {
    "sandbox": "workspace-write",
    "approval_policy": "never",
    "native_user_config": "ignored except the configured Windows sandbox backend; authentication remains in the original CODEX_HOME",
    "child_environment": "parent CODEX_* orchestration context removed except CODEX_HOME; authentication variables retained",
    "external_skills": "explicitly disabled except project-local treatment skills",
    "plugins_mcp": "disabled equally in every runnable arm",
    "project_documents": "disabled equally; Auto-Skills supplies its generated developer policy",
    "memory": "disabled equally",
    "usage": "native completion events; missing fields remain null; no cost estimate",
    "validators": "outside the agent worktree; immutable source hashes checked before/after",
    "timing": "elapsed includes fixture creation, setup, inference and final validation; stages also separate",
    "ordering": "deterministic arm rotation between repetitions; no independent cache reset",
    "confounds": [
        "Auto-Skills includes its developer policy and offline wrappers; it is a treatment bundle, not skills alone.",
        "Offline Auto-Skills does not install RTK/repomix or discover remote winners.",
        "Vercel uses manually selected React guidance and is applicable only to the frontend task.",
        "Autoskills detects the frontend workspace and installs its own pinned-registry recommendations; this adapter covers only that fixture.",
        "SkillRadar uses an unmodified project-local router bundle with an offline pinned registry; it is not a native marketplace install and may not activate on these coding prompts.",
        "Same authentication/home and service caches are retained; cache hits are observed, never assumed.",
        "A requested model identifier is recorded exactly; a mutable service alias is not an immutable model snapshot.",
        "External validators are public and outside the writable worktree, not secret tests or a malicious-code sandbox.",
        "Three small synthetic fixes cannot establish general quality, cost or latency superiority.",
    ],
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory(root):
    return {
        path.relative_to(root).as_posix(): sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and not path.is_symlink()
    }


def fingerprint(files):
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def load_tasks():
    tasks = json.loads((EXAMPLES / "tasks.json").read_text(encoding="utf-8"))
    for task in tasks:
        for key in ("fixture", "reference_fix", "validator"):
            path = (EXAMPLES / task[key]).resolve()
            if not path.is_relative_to(EXAMPLES.resolve()) or not path.exists():
                raise ValueError("task fixture path is invalid")
        source = Path(task["source"])
        if source.is_absolute() or ".." in source.parts:
            raise ValueError("task source must stay inside its fixture")
    return tasks


def load_competitors():
    return json.loads(COMPETITORS.read_text(encoding="utf-8"))["competitors"]


def run_checked(command, *, cwd=None, env=None, timeout=30):
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode:
        # Do not expose arbitrary subprocess output, which can contain user config.
        raise RuntimeError(f"{Path(command[0]).name} exited {result.returncode}")
    return result


def validate_task(task, worktree, timeout=30):
    """Run checks from outside the worktree without installing any dependencies."""
    validator = EXAMPLES / task["validator"]
    before = sha256(validator)
    runtime = task["runtime"]
    executable = sys.executable if runtime == "python" else shutil.which(runtime)
    if not executable:
        return {
            "status": "unavailable",
            "reason": f"required validator runtime {runtime} is unavailable",
        }
    started = time.monotonic()

    def budget():
        remaining = timeout - (time.monotonic() - started)
        if remaining <= 0:
            raise subprocess.TimeoutExpired("independent-validator", timeout)
        return remaining

    try:
        with tempfile.TemporaryDirectory(prefix="auto-skills-validator-") as temporary:
            directory = Path(temporary)
            if runtime == "rustc":
                # Only the selected source path is interpolated as a Rust string;
                # the independent test body never enters the writable worktree.
                source = (Path(worktree) / task["source"]).resolve().as_posix()
                generated = directory / "validator.rs"
                generated.write_text(
                    validator.read_text(encoding="utf-8").replace("__SOURCE__", source),
                    encoding="utf-8",
                )
                binary = directory / ("validator.exe" if os.name == "nt" else "validator")
                compiled = subprocess.run(
                    [executable, "--edition=2021", "--test", str(generated), "-o", str(binary)],
                    capture_output=True,
                    text=True,
                    timeout=budget(),
                    cwd=directory,
                )
                if compiled.returncode:
                    return {
                        "status": "failed",
                        "reason": "candidate failed independent Rust compilation",
                    }
                command = [str(binary)]
            else:
                command = [
                    executable,
                    *(["-I", "-B"] if runtime == "python" else []),
                    str(validator),
                    str(Path(worktree).resolve()),
                ]
            result = subprocess.run(
                command, cwd=directory, capture_output=True, text=True, timeout=budget()
            )
            if sha256(validator) != before:
                raise ValueError("independent validator integrity changed")
            return {
                "status": "passed" if result.returncode == 0 else "failed",
                "returncode": result.returncode,
                "elapsed_seconds": round(time.monotonic() - started, 6),
                "validator_sha256": before,
            }
    except subprocess.TimeoutExpired:
        return {"status": "failed", "reason": "independent validator timed out"}
    except OSError:
        return {"status": "unavailable", "reason": "validator runtime could not start"}


def parse_usage(stdout):
    """Prefer a cumulative thread total; otherwise sum actual completed turns."""
    turns, threads = [], []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        if not isinstance(event, dict) or not isinstance(event.get("usage"), dict):
            continue
        if event.get("type") == "thread.completed":
            threads.append(event["usage"])
        elif event.get("type") == "turn.completed":
            turns.append(event["usage"])
    rows = threads[-1:] or turns
    if not rows:
        return None
    usage = {}
    for key in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_output_tokens"):
        values = [row.get(key) for row in rows]
        usage[key] = (
            sum(values)
            if all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0
                for value in values
            )
            else None
        )
    usage["source"] = "thread.completed" if threads else "turn.completed"
    usage["events"] = len(rows)
    return usage


def native_environment(source=None):
    """Start an independent CLI, retaining persisted auth and normal tool variables."""
    result = {
        key: value
        for key, value in (os.environ if source is None else source).items()
        if (not key.upper().startswith("CODEX_") or key.upper() == "CODEX_HOME")
        and not key.upper().startswith("SKILLRADAR_")
    }
    result["SKILLRADAR_OFFLINE"] = "1"
    return result


def native_platform_flags(*, windows=None):
    """Ignoring user config must not discard the configured Windows sandbox backend."""
    if not (os.name == "nt" if windows is None else windows):
        return []
    home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    mode = read_toml(home / "config.toml").get("windows", {}).get("sandbox")
    if mode in {"elevated", "unelevated"}:
        return ["-c", "windows.sandbox=" + json.dumps(mode)]
    return []


@contextmanager
def task_directory(work_root, record):
    """Cleanup failures are operational evidence, independent of task correctness."""
    temporary = tempfile.TemporaryDirectory(prefix="auto-skills-task-", dir=work_root)
    try:
        yield temporary.name
    finally:
        try:
            temporary.cleanup()
            record["cleanup_status"] = "completed"
        except OSError:
            record["cleanup_status"] = "incomplete"
            record["cleanup_reason"] = "temporary task directory could not be completely removed"


def execute_native(command, prompt, cwd, timeout):
    """Kill the owned process group on timeout; retain no raw event transcripts."""
    options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=native_environment(),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **options,
    )
    timed_out = False
    try:
        stdout, stderr = process.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=15
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.kill()
        stdout, stderr = process.communicate(timeout=15)
    failures = 0
    diagnostics = set()
    event_types = Counter()
    item_types = Counter()
    error_fingerprints = set()
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
            if isinstance(event, dict):
                event_types[event.get("type", "unknown")] += 1
                item = event.get("item", {})
                if isinstance(item, dict) and event.get("type") == "item.completed":
                    item_types[item.get("type", "unknown")] += 1
                if isinstance(item, dict) and item.get("type") == "agent_message":
                    final_text = str(item.get("text", "")).lower()
                    if (
                        "read-only filesystem access" in final_text
                        or "command runner rejected" in final_text
                    ):
                        diagnostics.add("agent_reported_sandbox_restriction")
            if isinstance(event, dict) and event.get("type") in {
                "error",
                "turn.failed",
                "thread.failed",
            }:
                failures += 1
                payload = json.dumps(event, sort_keys=True)
                diagnostics.add(diagnostic_category(payload))
                error_fingerprints.add(hashlib.sha256(payload.encode()).hexdigest())
        except ValueError:
            continue
    if process.returncode and stderr:
        diagnostics.add(diagnostic_category(stderr))
    return {
        "returncode": process.returncode,
        "timed_out": timed_out,
        "usage": parse_usage(stdout),
        "native_failure_events": failures,
        "stderr_lines": len(stderr.splitlines()),
        "diagnostic_categories": sorted(diagnostics),
        "native_event_types": dict(event_types),
        "native_item_types": dict(item_types),
        "native_error_fingerprints": sorted(error_fingerprints),
    }


def diagnostic_category(message):
    """Retain an actionable category without persisting arbitrary native text."""
    lowered = message.lower()
    for category, needles in (
        ("authentication", ("unauthorized", "authentication", "401", "log in", "token expired")),
        (
            "quota_or_rate_limit",
            (
                "quota",
                "rate limit",
                "usage limit",
                "usage_limit",
                "429",
                "credit balance",
                "billing",
            ),
        ),
        (
            "context_length",
            (
                "context window",
                "context length",
                "context_length",
                "input too large",
                "maximum context",
                "too many tokens",
            ),
        ),
        (
            "service_unavailable",
            (
                "internal server",
                "server error",
                "service unavailable",
                "overloaded",
                "502",
                "503",
                "504",
            ),
        ),
        (
            "stream_or_transport",
            ("stream disconnected", "stream error", "socket", "transport", "connection closed"),
        ),
        ("sandbox_or_permission", ("sandbox", "permission denied", "access denied")),
        ("network", ("network", "connection", "dns", "timed out")),
        (
            "model_unavailable",
            ("model not found", "model is not", "unsupported model", "does not exist"),
        ),
        ("configuration", ("config", "profile", "mcp")),
    ):
        if any(needle in lowered for needle in needles):
            return category
    return "native_execution_error"


def metric(values):
    present = [
        value for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    return {
        "n": len(present),
        "median": statistics.median(present) if present else None,
        "min": min(present) if present else None,
        "max": max(present) if present else None,
    }


def summarize(runs):
    grouped = {}
    for row in runs:
        grouped.setdefault((row["task"], row["arm"]), []).append(row)
    result = []
    for (task, arm), rows in grouped.items():
        statuses = Counter(row["status"] for row in rows)
        passed = [
            row
            for row in rows
            if row["status"] == "passed"
            and row.get("after_validation", {}).get("status") == "passed"
        ]
        failed = [row for row in rows if row["status"] in {"failed", "timeout"}]
        summary = {
            "task": task,
            "arm": arm,
            "runs": len(rows),
            "successes": statuses["passed"],
            "failures": sum(
                count
                for status, count in statuses.items()
                if status not in {"passed", "unavailable", "interrupted", "not_attempted"}
            ),
            "unavailable": statuses["unavailable"],
            "interrupted": statuses["interrupted"],
            "not_attempted": statuses["not_attempted"],
            "statuses": dict(statuses),
            "performance_basis": "independently validated passed rows only",
            "validated_successes": len(passed),
            "elapsed_seconds": metric(row.get("elapsed_seconds") for row in passed),
            "inference_seconds": metric(row.get("inference_seconds") for row in passed),
            "setup_seconds": metric(row.get("setup_seconds") for row in passed),
            "attempt_elapsed_seconds": metric(row.get("elapsed_seconds") for row in rows),
            "failed_elapsed_seconds": metric(row.get("elapsed_seconds") for row in failed),
            "reported_usage_totals": {},
        }
        for key in (
            "input_tokens",
            "output_tokens",
            "cached_input_tokens",
            "reasoning_output_tokens",
        ):
            summary[key] = metric((row.get("usage") or {}).get(key) for row in passed)
            summary["attempt_" + key] = metric((row.get("usage") or {}).get(key) for row in rows)
            values = [(row.get("usage") or {}).get(key) for row in rows]
            known = [
                value
                for value in values
                if isinstance(value, int) and not isinstance(value, bool) and value >= 0
            ]
            summary["reported_usage_totals"][key] = {
                "n": len(known),
                "total": sum(known) if known else None,
            }
        result.append(summary)
    return result


def fixture_commit(worktree, budget=lambda: 30):
    env = {
        **os.environ,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "Synthetic Benchmark",
        "GIT_AUTHOR_EMAIL": "benchmark@example.invalid",
        "GIT_COMMITTER_NAME": "Synthetic Benchmark",
        "GIT_COMMITTER_EMAIL": "benchmark@example.invalid",
        "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+00:00",
    }
    for args in (
        ["init", "-q", "--initial-branch=benchmark", "--template="],
        ["config", "core.autocrlf", "false"],
        ["add", "--all"],
        ["-c", "commit.gpgsign=false", "commit", "-q", "-m", "Public synthetic benchmark fixture"],
    ):
        run_checked(["git", *args], cwd=worktree, env=env, timeout=min(30, budget()))
    return run_checked(
        ["git", "rev-parse", "HEAD"], cwd=worktree, env=env, timeout=min(30, budget())
    ).stdout.strip()


def install_competitor(arm, task, worktree, temporary, budget):
    entry = load_competitors()[arm]
    if not entry.get("adapter"):
        return {"status": "unavailable", "reason": entry["unavailable_reason"]}
    if task["id"] not in entry.get("applicable_tasks", []):
        return {
            "status": "unavailable",
            "reason": "pinned competitor configuration is not applicable to this task",
        }
    npx = "npx.cmd" if os.name == "nt" else "npx"
    source = temporary / "competitor-source"
    source.mkdir()
    env = {
        **os.environ,
        "npm_config_cache": str(temporary / "npm-cache"),
        "npm_config_prefix": str(temporary / "npm-prefix"),
        "npm_config_ignore_scripts": "true",
        "npm_config_update_notifier": "false",
        "DISABLE_TELEMETRY": "1",
        "CI": "1",
        "HOME": str(temporary / "competitor-home"),
        "USERPROFILE": str(temporary / "competitor-home"),
        "CODEX_HOME": str(temporary / "competitor-home/.codex"),
        "XDG_CONFIG_HOME": str(temporary / "competitor-home/config"),
        "XDG_CACHE_HOME": str(temporary / "competitor-home/cache"),
        "APPDATA": str(temporary / "competitor-home/appdata"),
        "LOCALAPPDATA": str(temporary / "competitor-home/localappdata"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "AUTOSKILLS_CACHE_DIR": str(temporary / "autoskills-cache"),
        "AUTOSKILLS_REGISTRY_BASE_URL": (
            "https://raw.githubusercontent.com/midudev/autoskills/"
            + entry["source_commit"]
            + "/packages/autoskills/skills-registry"
        ),
    }
    for key in ("OPENAI_API_KEY", "GITHUB_TOKEN", "GH_TOKEN"):
        env.pop(key, None)
    run_checked(
        ["git", "init", "-q", "--template="], cwd=source, env=env, timeout=min(60, budget())
    )
    run_checked(
        ["git", "fetch", "--depth=1", entry["source_repository"], entry["source_commit"]],
        cwd=source,
        env=env,
        timeout=min(60, budget()),
    )
    run_checked(
        ["git", "checkout", "--detach", "FETCH_HEAD"],
        cwd=source,
        env=env,
        timeout=min(60, budget()),
    )
    actual = run_checked(
        ["git", "rev-parse", "HEAD"], cwd=source, env=env, timeout=min(60, budget())
    ).stdout.strip()
    if actual != entry["source_commit"]:
        raise ValueError("competitor source commit differs from its pin")
    if arm == "skillradar":
        package = source / "packages/codex-plugin"
        destination = worktree / ".agents/skills/skillradar"
        names = ("skills/skill-router/SKILL.md", "scripts/skillradar.mjs", "data/registry.json")
        for name in names:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(package / name, target)
            if sha256(target) != sha256(package / name):
                raise ValueError("SkillRadar bundle differs from pinned source")
        env["SKILLRADAR_OFFLINE"] = "1"
        for key in ("SKILLRADAR_BASE_URL", "SKILLRADAR_REGISTRY_PATH"):
            env.pop(key, None)
        result = run_checked(
            ["node", str(destination / "scripts/skillradar.mjs"), "match", task["prompt"]],
            cwd=worktree / task["scope"],
            env=env,
            timeout=min(30, budget()),
        )
        evidence = json.loads(result.stdout)
        if (
            evidence.get("source") != "skillradar-registry"
            or evidence.get("registry", {}).get("mode") != "local-bundled"
            or evidence.get("ranking", {}).get("version") != "2.1"
        ):
            raise ValueError("SkillRadar did not use the pinned bundled registry")
        return {
            "status": "ready",
            "pin": entry,
            "installed_skill_count": 1,
            "installed_files_sha256": {name: sha256(destination / name) for name in names},
            "routing_source": "skillradar-registry",
            "registry_mode": "local-bundled",
            "ranking_version": "2.1",
        }
    destination = worktree / task["scope"] if arm == "autoskills" else worktree
    if arm == "autoskills":
        command = [
            npx,
            "--yes",
            f"{entry['npm_package']}@{entry['npm_version']}",
            "--yes",
            "--agent",
            "codex",
        ]
    else:
        command = [
            npx,
            "--yes",
            f"{entry['npm_package']}@{entry['npm_version']}",
            "add",
            str(source),
            "--skill",
            entry["skill"],
            "--agent",
            "codex",
            "--yes",
            "--copy",
        ]
    run_checked(command, cwd=destination, env=env, timeout=min(60, budget()))
    paths = list((destination / ".agents/skills").rglob("SKILL.md"))
    if not paths:
        raise ValueError("competitor installer did not produce a project-local Codex skill")
    return {
        "status": "ready",
        "pin": entry,
        "installed_skill_count": len(paths),
        "installed_skill_inventory_sha256": fingerprint(inventory(destination / ".agents/skills")),
    }


@contextmanager
def control_profile(worktree, cwd):
    """Disable native extras while allowing treatment skills installed in this project."""
    home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    home.mkdir(parents=True, exist_ok=True)
    project_skills = {
        str(path.resolve())
        for base in {worktree, cwd}
        for path in (base / ".agents/skills").rglob("SKILL.md")
    }
    entries = [
        {"path": path, "enabled": path in project_skills}
        for path in sorted(external_skills(worktree, cwd))
    ]
    data = {
        "skills": {"bundled": {"enabled": False}, "config": entries},
        "plugins": {"_default": {"enabled": False}},
        "mcp_servers": {},
    }

    def disable_integrations(layer):
        for name, server in layer.get("mcp_servers", {}).items():
            data["mcp_servers"][name] = {**server, "enabled": False}
        for name in layer.get("plugins", {}):
            data["plugins"][name] = {"enabled": False}
        for profile in layer.get("profiles", {}).values():
            disable_integrations(profile)

    for layer in config_layers(worktree, cwd):
        disable_integrations(layer)
    descriptor, filename = tempfile.mkstemp(
        prefix="benchmark-control-", suffix=".config.toml", dir=home
    )
    os.close(descriptor)
    path = Path(filename)
    try:
        path.write_text(
            "\n".join(json.dumps(key) + "=" + toml_value(value) for key, value in data.items())
            + "\n",
            encoding="utf-8",
        )
        yield ["--profile", path.name.removesuffix(".config.toml")]
    finally:
        path.unlink(missing_ok=True)


def run_one(args, task, arm, repetition, version):
    initial = inventory(EXAMPLES / task["fixture"])
    record = {
        "task": task["id"],
        "arm": arm,
        "repetition": repetition,
        "model": args.model,
        "codex_version": version,
        "fixture_sha256": fingerprint(initial),
        "validator_sha256": sha256(EXAMPLES / task["validator"]),
        "prompt_sha256": hashlib.sha256(task["prompt"].encode()).hexdigest(),
        "usage": None,
        "elapsed_seconds": None,
        "fixture_commit": None,
    }
    if arm not in {"baseline", "auto-skills"}:
        entry = load_competitors()[arm]
        if not entry.get("adapter") or task["id"] not in entry.get("applicable_tasks", []):
            record.update(
                status="unavailable",
                reason=entry.get(
                    "unavailable_reason",
                    "pinned competitor configuration is not applicable to this task",
                ),
            )
            return record
    started = time.monotonic()

    def remaining():
        budget = args.timeout - (time.monotonic() - started)
        if budget <= 0:
            raise subprocess.TimeoutExpired("task-budget", args.timeout)
        return budget

    try:
        with task_directory(args.work_root, record) as temporary:
            directory = Path(temporary)
            worktree = directory / "worktree"
            shutil.copytree(EXAMPLES / task["fixture"], worktree)
            record["fixture_commit"] = fixture_commit(worktree, remaining)
            before = validate_task(task, worktree, timeout=min(30, remaining()))
            record["before_validation"] = before
            if before["status"] != "failed":
                record.update(
                    status="unavailable",
                    reason="fixture does not have an executable failing validator",
                )
                return record
            setup_start = time.monotonic()
            cwd = worktree / task["scope"]
            lock = None
            if arm == "auto-skills":
                lock = bootstrap(worktree, offline=True, cache_dir=directory / "cache")
                record["selected_slots"] = [
                    {
                        "scope": entry.get("scope", "."),
                        "slot": entry["slot"],
                        "source": entry["source"],
                    }
                    for entry in lock["skills"]
                ]
                record["tools"] = [
                    {"name": tool["name"], "status": tool["status"]} for tool in lock["tools"]
                ]
            elif arm != "baseline":
                record["competitor_setup"] = install_competitor(
                    arm, task, worktree, directory, remaining
                )
            record["setup_seconds"] = round(time.monotonic() - setup_start, 6)
            flags = [
                "exec",
                "--json",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                *native_platform_flags(),
                "--sandbox",
                "workspace-write",
                "--model",
                args.model,
                "-C",
                str(cwd),
                "--disable",
                "memories",
                "-c",
                'approval_policy="never"',
                "-c",
                "project_doc_max_bytes=0",
                "-c",
                f'model_reasoning_effort="{args.reasoning_effort}"',
                "-",
            ]
            profile = (
                launch_profile(worktree, lock, flags, cwd)
                if lock
                else control_profile(worktree, cwd)
            )
            inference_start = time.monotonic()
            with profile as launch:
                command = [args.codex, *(launch if lock else [*launch, *flags])]
                prompt = task["prompt"]
                if task["scope"] != ".":
                    prompt = (
                        f"Your current directory is the {task['scope']} workspace. "
                        "Paths in this task are relative to the parent repository root.\n\n"
                        + prompt
                    )
                result = execute_native(command, prompt, cwd, remaining())
            record.update(result)
            record["inference_seconds"] = round(time.monotonic() - inference_start, 6)
            validation = validate_task(task, worktree, timeout=min(30, remaining()))
            record["after_validation"] = validation
            changes = [
                name
                for name, digest in initial.items()
                if not (worktree / name).is_file() or sha256(worktree / name) != digest
            ]
            record["changed_fixture_files"] = changes
            unchanged_contract = set(changes).issubset({task["source"]})
            record["status"] = (
                "timeout"
                if result["timed_out"]
                else "passed"
                if result["returncode"] == 0
                and result["native_failure_events"] == 0
                and validation["status"] == "passed"
                and unchanged_contract
                else "failed"
            )
            if not unchanged_contract:
                record["reason"] = "unrelated fixture source or manifest changed"
            elif record["status"] != "passed":
                record["reason"] = (
                    "native execution timed out"
                    if result["timed_out"]
                    else "native execution reported failure"
                    if result["returncode"] or result["native_failure_events"]
                    else "independent validator rejected the candidate"
                )
            record["usage_available"] = result["usage"] is not None
    except (FileNotFoundError, OSError) as exc:
        record.update(
            status="unavailable", reason=f"required process unavailable ({type(exc).__name__})"
        )
    except subprocess.TimeoutExpired:
        record.update(status="timeout", reason="setup or validation exceeded its deadline")
    except (RuntimeError, ValueError) as exc:
        record.update(
            status="failed", reason=f"setup or native execution failed ({type(exc).__name__})"
        )
    finally:
        record["elapsed_seconds"] = round(time.monotonic() - started, 6)
    return record


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--model",
        required=True,
        help="Exact service model identifier; prefer an immutable snapshot",
    )
    result.add_argument("--arms", default="baseline,auto-skills")
    result.add_argument("--repetitions", type=int, default=3)
    result.add_argument("--output", required=True, type=Path)
    result.add_argument(
        "--timeout", type=float, default=180, help="Per-task wall-clock budget in seconds"
    )
    result.add_argument(
        "--task", action="append", help="Task id to include; repeat to include several"
    )
    result.add_argument("--dry-run", action="store_true")
    result.add_argument(
        "--resume",
        type=Path,
        help="Resume only unrecorded plan slots from an existing report; preserve all measured rows",
    )
    result.add_argument(
        "--assume-first-pending-interrupted",
        action="store_true",
        help="Account for an ambiguous first pending slot without replaying a possibly started request",
    )
    result.add_argument(
        "--blocked-preflight",
        type=Path,
        help="Record the plan as unattempted using a prior failed preflight report; make no native calls",
    )
    result.add_argument("--codex", default="codex")
    result.add_argument(
        "--work-root",
        type=Path,
        help="Optional parent for temporary task repositories; validators remain outside them",
    )
    result.add_argument("--expected-codex-version", default="0.166.0")
    result.add_argument("--reasoning-effort", choices=("low", "medium", "high"), default="low")
    return result


def markdown_report(report):
    lines = [
        "# Complete-task benchmark",
        "",
        f"Mode: **{report['mode']}**. Model: `{report['model']}`. Repetitions: {report['repetitions']}.",
        "",
        (
            "Planned matrix only: attempts below were not executed because the operator designated a failed preflight. No comparative performance result is available."
            if report["mode"] == "blocked"
            else "Performance medians use independently validated successful attempts only. All failures, interruption and inapplicable slots remain counted separately; missing usage is unavailable. No savings, price or winner is inferred."
        ),
        "",
        "| Task | Arm | Passed | Failed | Unavailable | Interrupted | Not attempted | Passed total seconds [min, max] | Passed inference / setup seconds | Passed input / output / cached tokens |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for summary in report["summary"]:
        elapsed = summary["elapsed_seconds"]
        tokens = " / ".join(
            str(summary[key]["median"])
            for key in ("input_tokens", "output_tokens", "cached_input_tokens")
        )
        lines.append(
            f"| {summary['task']} | {summary['arm']} | {summary['successes']} | {summary['failures']} | {summary['unavailable']} | {summary.get('interrupted', 0)} | {summary.get('not_attempted', 0)} | {elapsed['median']} [{elapsed['min']}, {elapsed['max']}] | {summary.get('inference_seconds', {}).get('median')} / {summary.get('setup_seconds', {}).get('median')} | {tokens} |"
        )
    if report["mode"] == "dry-run":
        lines += [
            "",
            f"Planned executions: {len(report['plan'])}. No inference or competitor installation was attempted.",
        ]
    if report["mode"] == "blocked":
        lines += [
            "",
            "The operator supplied a failed preflight. Planned attempts were not executed and have no repeated measurements.",
            f"Preflight report SHA256: `{report['preflight']['sha256']}`. Actual preflight usage is retained separately in JSON evidence.",
        ]
    if report.get("resume_batches"):
        lines += [
            "",
            "This is an observational interrupted run. All prior failures are preserved; a possibly started unrecorded slot is accounted for separately and is never replayed. Resumed batches have separate harness/source receipts. Native error causes from the original batch remain unresolved when only a generic category was recorded.",
            "",
        ]
    lines += ["", "## Measurement limits", "", *["- " + note for note in POLICY["confounds"]], ""]
    return "\n".join(lines)


def resume_benchmark(args, current, tasks):
    """Account for interruption and continue only genuinely unrecorded slots."""
    if not args.resume.is_file():
        raise ValueError("resume report is missing")
    report = json.loads(args.resume.read_text(encoding="utf-8"))
    required_pins = (
        "model",
        "expected_codex_version",
        "auto_skills_version",
        "repetitions",
        "timeout_seconds",
        "reasoning_effort",
        "public_tasks_sha256",
        "competitors_sha256",
        "native_platform_flags",
        "policy",
        "plan",
    )
    if report.get("mode") != "live" or report.get("codex_version") != args.expected_codex_version:
        raise ValueError("resume live/native version pin does not match")
    for key in required_pins:
        if report.get(key) != current.get(key):
            raise ValueError("resume pin does not match: " + key)
    rows = report.get("runs", [])
    if not isinstance(rows, list) or len(rows) > len(report["plan"]):
        raise ValueError("resume rows do not form a valid plan prefix")
    for row, planned in zip(rows, report["plan"], strict=False):
        if any(
            row.get(key) != planned.get(key)
            for key in ("task", "arm", "repetition", "fixture_sha256")
        ):
            raise ValueError("resume row/fixture pin does not match the plan prefix")
    tasks_by_id = {task["id"]: task for task in tasks}
    for row in rows:
        task = tasks_by_id[row["task"]]
        for key, expected in (
            ("validator_sha256", sha256(EXAMPLES / task["validator"])),
            ("prompt_sha256", hashlib.sha256(task["prompt"].encode()).hexdigest()),
        ):
            if key in row and row[key] != expected:
                raise ValueError("resume task pin does not match: " + key)
    if len(rows) == len(report["plan"]):
        raise ValueError("resume report has no remaining plan slots")
    initial_rows = len(rows)
    batch = {
        "started_at": datetime.now(UTC).isoformat(),
        "source_report_sha256": sha256(args.resume),
        "preserved_rows": initial_rows,
        "harness_sha256": current["harness_sha256"],
        "bootstrap_source_sha256": current["bootstrap_source_sha256"],
        "auto_skills_version": current["auto_skills_version"],
        "policy": "preserve prior rows; never retry recorded failures; stop new requests on native failure",
    }
    report.setdefault("resume_batches", []).append(batch)
    batch_id = len(report["resume_batches"])
    if args.work_root:
        args.work_root.mkdir(parents=True, exist_ok=True)

    def applicable(entry):
        return entry["arm"] in {"baseline", "auto-skills"} or entry["task"] in report[
            "competitors"
        ][entry["arm"]].get("applicable_tasks", [])

    first_pending = report["plan"][len(rows)]
    in_flight = report.get("in_flight")
    if in_flight is not None and any(
        in_flight.get(key) != first_pending.get(key) for key in ("task", "arm", "repetition")
    ):
        raise ValueError("resume in-flight slot does not match the first pending plan slot")
    if args.assume_first_pending_interrupted or in_flight is not None:
        if not applicable(first_pending):
            raise ValueError("an inapplicable slot cannot have an interrupted native attempt")
        rows.append(
            {
                **first_pending,
                "status": "interrupted",
                "attempt_state": "unknown",
                "reason": "runner disappeared before this slot was recorded; it may have started; not replayed",
                "elapsed_seconds": None,
                "usage": None,
                "batch": batch_id,
            }
        )
        batch["interrupted_slot_accounted_for"] = True
        report.pop("in_flight", None)
    stop_reason = None
    try:
        version = run_checked([args.codex, "--version"], timeout=15).stdout.strip()
        if version != "codex-cli " + args.expected_codex_version:
            raise ValueError("native CLI version differs from pin")
    except (OSError, subprocess.TimeoutExpired, RuntimeError, ValueError):
        stop_reason = (
            "not attempted: resumed native CLI health check could not start with the pinned version"
        )
    for entry in report["plan"][len(rows) :]:
        if not applicable(entry):
            row = {
                **entry,
                "status": "unavailable",
                "reason": "pinned competitor configuration is not applicable to this task",
                "elapsed_seconds": None,
                "usage": None,
            }
        elif stop_reason:
            row = {
                **entry,
                "status": "not_attempted",
                "reason": stop_reason,
                "elapsed_seconds": None,
                "usage": None,
            }
        else:
            report["in_flight"] = {key: entry[key] for key in ("task", "arm", "repetition")}
            report["summary"] = summarize(rows)
            write_report(args.output, report)
            print(
                f"Resuming {entry['task']} / {entry['arm']} / repetition {entry['repetition']}",
                flush=True,
            )
            row = run_one(
                args,
                tasks_by_id[entry["task"]],
                entry["arm"],
                entry["repetition"],
                args.expected_codex_version,
            )
            report.pop("in_flight", None)
            if (
                row.get("returncode")
                or row.get("native_failure_events")
                or row.get("timed_out")
                or row.get("status") == "unavailable"
            ):
                stop_reason = "not attempted: resumed native execution failed; additional requests stopped without retries"
                batch["stop_diagnostic_categories"] = row.get("diagnostic_categories", [])
        row["batch"] = batch_id
        rows.append(row)
        report["summary"] = summarize(rows)
        write_report(args.output, report)
    batch["ended_at"] = datetime.now(UTC).isoformat()
    batch["added_rows"] = len(rows) - initial_rows
    batch["stopped_on_native_failure"] = stop_reason is not None
    report["plan_fully_accounted_for"] = len(rows) == len(report["plan"])
    report["execution_status"] = (
        "partial"
        if any(row["status"] in {"interrupted", "not_attempted"} for row in rows)
        else "complete"
    )
    report["summary"] = summarize(rows)
    write_report(args.output, report)
    return report


def run_benchmark(args):
    if args.repetitions < 1 or args.timeout <= 0:
        raise ValueError("repetitions and timeout must be positive")
    if args.blocked_preflight and args.dry_run:
        raise ValueError("blocked-preflight and dry-run are separate reporting modes")
    if args.resume and (args.blocked_preflight or args.dry_run):
        raise ValueError(
            "resume requires a live report and cannot combine with blocked-preflight or dry-run"
        )
    if args.assume_first_pending_interrupted and not args.resume:
        raise ValueError("interrupted pending accounting requires --resume")
    arms = [arm.strip() for arm in args.arms.split(",") if arm.strip()]
    if (
        not arms
        or len(set(arms)) != len(arms)
        or set(arms) - {"baseline", "auto-skills", *load_competitors()}
    ):
        raise ValueError("unknown, empty or duplicate benchmark arm")
    tasks = load_tasks()
    if args.task:
        requested = set(args.task)
        if requested - {task["id"] for task in tasks}:
            raise ValueError("unknown benchmark task")
        tasks = [task for task in tasks if task["id"] in requested]
    report = {
        "schema_version": 1,
        "mode": "dry-run" if args.dry_run else "live",
        "created_at": datetime.now(UTC).isoformat(),
        "model": args.model,
        "expected_codex_version": args.expected_codex_version,
        "codex_version": None,
        "auto_skills_version": __version__,
        "harness_sha256": sha256(Path(__file__)),
        "bootstrap_source_sha256": fingerprint(
            {
                path.relative_to(WORKSPACE / "src/codex_bootstrap").as_posix(): sha256(path)
                for path in sorted((WORKSPACE / "src/codex_bootstrap").rglob("*.py"))
            }
        ),
        "public_tasks_sha256": sha256(EXAMPLES / "tasks.json"),
        "competitors_sha256": sha256(COMPETITORS),
        "competitors": load_competitors(),
        "python_version": platform.python_version(),
        "platform": platform.system(),
        "repetitions": args.repetitions,
        "timeout_seconds": args.timeout,
        "reasoning_effort": args.reasoning_effort,
        "native_platform_flags": native_platform_flags(),
        "work_root": "explicit parent directory"
        if args.work_root
        else "system temporary directory",
        "policy": POLICY,
        "plan": [],
        "runs": [],
        "summary": [],
    }
    for repetition in range(args.repetitions):
        ordered = arms[repetition % len(arms) :] + arms[: repetition % len(arms)]
        for task in tasks:
            for arm in ordered:
                report["plan"].append(
                    {
                        "task": task["id"],
                        "arm": arm,
                        "repetition": repetition + 1,
                        "fixture_sha256": fingerprint(inventory(EXAMPLES / task["fixture"])),
                        "sandbox": "workspace-write",
                        "model": args.model,
                    }
                )
    if args.resume:
        return resume_benchmark(args, report, tasks)
    if args.blocked_preflight:
        if not args.blocked_preflight.is_file():
            raise ValueError("failed preflight report is missing")
        source = json.loads(args.blocked_preflight.read_text(encoding="utf-8"))
        if source.get("model") != args.model:
            raise ValueError("preflight model does not match this plan")
        if source.get("codex_version") not in {None, args.expected_codex_version}:
            raise ValueError("preflight CLI version does not match this plan")
        failed = [
            row
            for row in source.get("runs", [])
            if row.get("status") in {"failed", "timeout", "unavailable"}
        ]
        if not failed:
            raise ValueError("preflight report contains no failed or unavailable attempts")
        known_categories = {
            "agent_reported_sandbox_restriction",
            "authentication",
            "quota_or_rate_limit",
            "sandbox_or_permission",
            "network",
            "model_unavailable",
            "configuration",
            "native_execution_error",
        }
        evidence = []
        for row in failed:
            if row.get("task") not in {task["id"] for task in load_tasks()} or row.get(
                "arm"
            ) not in {"baseline", "auto-skills", *load_competitors()}:
                continue
            usage = row.get("usage")
            evidence.append(
                {
                    "task": row["task"],
                    "arm": row["arm"],
                    "status": row["status"],
                    "returncode": row.get("returncode")
                    if isinstance(row.get("returncode"), int)
                    else None,
                    "elapsed_seconds": row.get("elapsed_seconds")
                    if isinstance(row.get("elapsed_seconds"), (int, float))
                    else None,
                    "diagnostic_categories": sorted(
                        set(row.get("diagnostic_categories", [])) & known_categories
                    ),
                    "usage": {
                        key: usage.get(key)
                        for key in (
                            "input_tokens",
                            "output_tokens",
                            "cached_input_tokens",
                            "reasoning_output_tokens",
                        )
                        if isinstance(usage.get(key), int)
                    }
                    if isinstance(usage, dict)
                    else None,
                }
            )
        if not evidence:
            raise ValueError("preflight has no recognized task/arm evidence")
        report.update(
            mode="blocked",
            codex_version=source.get("codex_version"),
            preflight={
                "sha256": sha256(args.blocked_preflight),
                "evidence": evidence,
                "basis": "operator-designated failed preflight; no repeated inference attempted",
            },
        )
        report["runs"] = [
            {
                **entry,
                "status": "unavailable",
                "reason": "not attempted: operator-designated preflight failed",
                "elapsed_seconds": None,
                "usage": None,
            }
            for entry in report["plan"]
        ]
        report["summary"] = summarize(report["runs"])
    elif not args.dry_run:
        if args.work_root:
            args.work_root.mkdir(parents=True, exist_ok=True)
        try:
            version = run_checked([args.codex, "--version"], timeout=15).stdout.strip()
            if not re.fullmatch(r"codex-cli " + re.escape(args.expected_codex_version), version):
                raise ValueError("native Codex version differs from the explicit benchmark pin")
            report["codex_version"] = args.expected_codex_version
        except (OSError, subprocess.TimeoutExpired, RuntimeError, ValueError) as exc:
            report["preflight_error"] = type(exc).__name__
            version = None
        tasks_by_id = {task["id"]: task for task in tasks}
        for entry in report["plan"]:
            if version is None:
                record = {
                    **entry,
                    "status": "unavailable",
                    "reason": "native CLI missing or does not match the pinned version",
                    "elapsed_seconds": None,
                    "usage": None,
                }
            else:
                print(
                    f"Running {entry['task']} / {entry['arm']} / repetition {entry['repetition']}",
                    flush=True,
                )
                record = run_one(
                    args,
                    tasks_by_id[entry["task"]],
                    entry["arm"],
                    entry["repetition"],
                    args.expected_codex_version,
                )
            report["runs"].append(record)
            report["summary"] = summarize(report["runs"])
            write_report(args.output, report)
    write_report(args.output, report)
    return report


def write_report(output, report):
    output.mkdir(parents=True, exist_ok=True)
    atomic_write(output / "report.json", json.dumps(report, indent=2, sort_keys=True) + "\n")
    atomic_write(output / "report.md", markdown_report(report))


def main(argv=None):
    argument_parser = parser()
    args = argument_parser.parse_args(argv)
    try:
        report = run_benchmark(args)
    except ValueError as exc:
        argument_parser.error(str(exc))
    counts = Counter(row["status"] for row in report["runs"])
    print(
        json.dumps(
            {"mode": report["mode"], "planned": len(report["plan"]), "statuses": dict(counts)}
        )
    )
    return 1 if any(status != "passed" for status in counts) else 0


if __name__ == "__main__":
    raise SystemExit(main())
