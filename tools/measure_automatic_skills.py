"""Pinned public-manifest relevance and separately validated complete-task trials.

Default execution is offline and makes no model requests. --refresh downloads
only public manifests/licenses. --tasks explicitly uses existing Codex auth.
"""

# ruff: noqa: E402
import argparse
import hashlib
import json
import os
import platform
import signal
import subprocess
import sys
import tempfile
import time
from collections import Counter
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "src"))
sys.path.insert(0, str(WORKSPACE))

from codex_bootstrap.bootstrap import verify_lock
from codex_bootstrap.config import launch_profile
from codex_bootstrap.profile import BASE_SLOTS
from codex_bootstrap.task import prepare_task
from tools import benchmark_tasks as tasks
from tools.verify_native_install import isolated_environment
from tools.verify_real_repositories import PublicGitHub, safe_relative

FIXTURES = WORKSPACE / "examples/measurement"
DEFAULT_CODEX = Path.home() / "AppData/Local/Programs/OpenAI/Codex/bin/codex.exe"
LIMITATION = (
    "Relevance uses pinned manifest/license extracts reconstructed as sibling workspaces, "
    "not complete public repositories or completed upstream tasks. Complete-task inference "
    "uses the separate three synthetic fixtures and independent validators. No token, cost, "
    "latency or quality superiority is inferred from either small convenience sample."
)
# These annotations precede selection. Manifest constraint review needs its language;
# package test/build guidance is permitted where evidenced by the manifest.
SEEDS = [
    ("requests", "psf/requests", "pyproject.toml", "LICENSE", "Apache-2.0", "python", []),
    ("bat", "sharkdp/bat", "Cargo.toml", "LICENSE-MIT", "MIT", "rust", []),
    ("github-cli", "cli/cli", "go.mod", "LICENSE", "MIT", "go", []),
    ("express", "expressjs/express", "package.json", "LICENSE", "MIT", "javascript", []),
    (
        "vue-reactivity",
        "vuejs/core",
        "packages/reactivity/package.json",
        "LICENSE",
        "MIT",
        "typescript",
        ["language-javascript"],
    ),
]


def digest(body):
    return hashlib.sha256(body).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def refresh(fixtures=FIXTURES, client=None):
    client = client or PublicGitHub(max_requests=20, deadline_seconds=180)
    catalog = {"schema_version": 1, "repositories": [], "refresh_failures": []}
    for slug, repo, original, license_path, spdx, language, allowed in SEEDS:
        spec = {
            "slug": slug,
            "repository": repo,
            "original_path": original,
            "license_original_path": license_path,
            "license_spdx": spdx,
            "expected_roles": ["language-" + language],
            "allowed_specialties": ["language-" + language, *allowed],
            "annotation_basis": "Manifest constraint review; language guidance required; no dependency implementation work.",
        }
        catalog["repositories"].append(spec)
        try:
            commit = client.json(f"repos/{repo}/commits/HEAD")["sha"]
            if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
                raise ValueError("invalid immutable Git commit")
            spec["commit"] = commit
            for original_name, local_name, key in (
                (original, "manifest.txt", "manifest_sha256"),
                (license_path, "LICENSE.txt", "license_sha256"),
            ):
                body = client.read(
                    f"https://raw.githubusercontent.com/{repo}/{commit}/{original_name}"
                )
                folder = fixtures / slug
                folder.mkdir(parents=True, exist_ok=True)
                (folder / local_name).write_bytes(body)
                spec[key] = digest(body)
            spec["manifest_url"] = f"https://github.com/{repo}/blob/{commit}/{original}"
            spec["license_url"] = f"https://github.com/{repo}/blob/{commit}/{license_path}"
            write_json(fixtures / slug / "provenance.json", spec)
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            catalog["refresh_failures"].append({"repository": repo, "reason": type(exc).__name__})
    write_json(fixtures / "catalog.json", catalog)
    return catalog


def verify_spec(spec, fixtures):
    errors = []
    try:
        if len(spec["commit"]) != 40 or any(c not in "0123456789abcdef" for c in spec["commit"]):
            raise ValueError("invalid commit pin")
        safe_relative(spec["slug"])
        safe_relative(spec["original_path"])
        folder = fixtures / spec["slug"]
        if json.loads((folder / "provenance.json").read_text(encoding="utf-8")) != spec:
            errors.append("provenance/catalog mismatch")
        for name, key in (("manifest.txt", "manifest_sha256"), ("LICENSE.txt", "license_sha256")):
            if digest((folder / name).read_bytes()) != spec[key]:
                errors.append(f"SHA-256 mismatch: {name}")
    except (OSError, KeyError, ValueError, TypeError):
        errors.append("invalid or incomplete public snapshot")
    return errors


def score_selection(decision, expected_scope, expected_roles, allowed_specialties):
    """Count root common guides separately; all task-specific extras remain visible."""
    scopes = set(decision["scopes"])
    selected = decision["selected"]
    specialties = [s for s in selected if s["slot"] not in BASE_SLOTS]
    irrelevant = [
        {"scope": s["scope"], "slot": s["slot"]}
        for s in specialties
        if s["scope"] != expected_scope or s["slot"] not in allowed_specialties
    ]
    actual_roles = {s["slot"] for s in selected if s["scope"] == expected_scope}
    missing = sorted(set(expected_roles) - actual_roles)
    return {
        "expected_scope": expected_scope,
        "actual_scopes": sorted(scopes),
        "scope_precision": len(scopes & {expected_scope}) / len(scopes) if scopes else None,
        "scope_recall": int(expected_scope in scopes),
        "specialty_count": len(specialties),
        "irrelevant_specialties": irrelevant,
        "specialty_precision": (len(specialties) - len(irrelevant)) / len(specialties)
        if specialties
        else None,
        "expected_roles": expected_roles,
        "allowed_specialties": allowed_specialties,
        "missed_capabilities": missing,
        "role_recall": (len(expected_roles) - len(missing)) / len(expected_roles)
        if expected_roles
        else None,
        "selected": [
            {"scope": s["scope"], "slot": s["slot"], "source": s["source"]} for s in selected
        ],
    }


def artifact_state(root):
    return {
        p.relative_to(root).as_posix(): (digest(p.read_bytes()), p.stat().st_mtime_ns)
        for directory in (root / ".codex", root / ".agents")
        for p in directory.rglob("*")
        if p.is_file()
    }


@contextmanager
def preparation_environment(home, cache):
    env = isolated_environment(home)
    env["CODEX_BOOTSTRAP_CACHE"] = str(cache)
    with patch.dict(os.environ, env, clear=True):
        yield


def relevance(fixtures=FIXTURES):
    catalog = json.loads((fixtures / "catalog.json").read_text(encoding="utf-8"))
    report = {
        "repositories": [],
        "refresh_failures": catalog.get("refresh_failures", []),
        "network_mode": "offline",
    }
    with tempfile.TemporaryDirectory(prefix="auto-skills-measurement-") as temporary:
        directory = Path(temporary)
        root, home, cache = directory / "repo", directory / "home", directory / "cache"
        root.mkdir()
        home.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        valid = []
        for spec in catalog["repositories"]:
            errors = verify_spec(spec, fixtures)
            row = {
                **spec,
                "integrity_errors": errors,
                "status": "unavailable" if errors else "pending",
            }
            report["repositories"].append(row)
            if not errors:
                target = root / spec["slug"] / spec["original_path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((fixtures / spec["slug"] / "manifest.txt").read_bytes())
                valid.append((spec, row, target))
        for index, (spec, row, target) in enumerate(valid):
            scope = target.parent.relative_to(root).as_posix()
            prompt = f"Review compatibility constraints in {target.relative_to(root).as_posix()}. Preserve all sibling workspaces."
            before_manifest = digest(target.read_bytes())
            with (
                preparation_environment(home, cache),
                patch(
                    "urllib.request.urlopen",
                    side_effect=AssertionError("offline preparation attempted network"),
                ) as network,
            ):
                started = time.monotonic()
                first = prepare_task(
                    root, prompt, offline=True, cache_dir=cache, session_id=spec["slug"]
                )
                first_seconds = time.monotonic() - started
                artifacts = artifact_state(root)
                started = time.monotonic()
                returned = prepare_task(
                    root, prompt, offline=True, cache_dir=cache, session_id=spec["slug"]
                )
                return_seconds = time.monotonic() - started
            row.update(
                score_selection(first, scope, spec["expected_roles"], spec["allowed_specialties"])
            )
            row.update(
                {
                    "status": "measured",
                    "task_prompt": prompt,
                    "preparation_kind": "cold repository and cache"
                    if index == 0
                    else "new task in prepared sibling matrix",
                    "first_preparation_seconds": round(first_seconds, 6),
                    "unchanged_return_seconds": round(return_seconds, 6),
                    "first_task_cache_hit": first["cache_hit"],
                    "unchanged_task_cache_hit": returned["cache_hit"],
                    "owned_artifacts_unchanged_on_return": artifacts == artifact_state(root),
                    "manifest_unchanged": before_manifest == digest(target.read_bytes()),
                    "network_download_attempts": network.call_count,
                    "remote_bundle_downloads": 0,
                    "remote_bundle_cache_reuse": "not exercised: offline bundled catalog only",
                    "model_requests": first["metrics"]["model_requests"]
                    + returned["metrics"]["model_requests"],
                    "uncertainties": first["uncertainties"],
                }
            )
    rows = [r for r in report["repositories"] if r["status"] == "measured"]
    report["summary"] = {
        "planned": len(catalog["repositories"]),
        "measured": len(rows),
        "unavailable": len(catalog["repositories"]) - len(rows),
        "scope_exact": sum(r["actual_scopes"] == [r["expected_scope"]] for r in rows),
        "irrelevant_specialties": sum(len(r["irrelevant_specialties"]) for r in rows),
        "missed_capabilities": sum(len(r["missed_capabilities"]) for r in rows),
        "task_cache_hits_on_return": sum(r["unchanged_task_cache_hit"] for r in rows),
    }
    return report


def logged_native(command, prompt, cwd, timeout, evidence):
    """Same native request, with symmetric sandbox and private raw evidence."""
    command = ["danger-full-access" if arg == "workspace-write" else arg for arg in command]
    options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=tasks.native_environment(),
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
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "events.jsonl").write_text(stdout, encoding="utf-8")
    (evidence / "stderr.txt").write_text(stderr, encoding="utf-8")
    failures, events, items, diagnostics = [], Counter(), Counter(), set()
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type", "unknown")
        events[kind] += 1
        if kind == "item.completed" and isinstance(event.get("item"), dict):
            items[event["item"].get("type", "unknown")] += 1
        if kind in {"error", "turn.failed", "thread.failed"}:
            payload = json.dumps(event, sort_keys=True)
            failures.append(digest(payload.encode()))
            diagnostics.add(tasks.diagnostic_category(payload))
    if process.returncode and stderr:
        diagnostics.add(tasks.diagnostic_category(stderr))
    return {
        "returncode": process.returncode,
        "timed_out": timed_out,
        "usage": tasks.parse_usage(stdout),
        "native_failure_events": len(failures),
        "native_event_types": dict(events),
        "native_item_types": dict(items),
        "native_error_fingerprints": sorted(set(failures)),
        "diagnostic_categories": sorted(diagnostics),
        "stderr_lines": len(stderr.splitlines()),
        "raw_event_sha256": digest(stdout.encode()),
        "raw_stderr_sha256": digest(stderr.encode()),
    }


def complete_tasks(codex, model, evidence, output, timeout=240):
    version = tasks.run_checked([str(codex), "--version"], timeout=15).stdout.strip()
    report = {
        "model": model,
        "codex_version": version,
        "repetitions": 1,
        "harness_sha256": tasks.sha256(Path(tasks.__file__)),
        "wrapper_sha256": tasks.sha256(Path(__file__)),
        "bootstrap_source_sha256": tasks.fingerprint(
            {p.name: tasks.sha256(p) for p in (WORKSPACE / "src/codex_bootstrap").glob("*.py")}
        ),
        "policy": {
            **tasks.POLICY,
            "sandbox": "danger-full-access equally for both arms in disposable synthetic fixtures",
            "auto_skills_treatment": "offline prepare_task and task-scoped launch_profile; no hook, no remote skill search; isolated preparation inventory",
        },
        "runs": [],
        "plan": [],
    }
    public_tasks = tasks.load_tasks()
    for index, task in enumerate(public_tasks):
        arms = ["baseline", "auto-skills"] if index % 2 == 0 else ["auto-skills", "baseline"]
        report["plan"].extend({"task": task["id"], "arm": arm, "repetition": 1} for arm in arms)
    stop = False
    for entry in report["plan"]:
        task = next(t for t in public_tasks if t["id"] == entry["task"])
        if stop:
            row = {
                **entry,
                "status": "not_attempted",
                "reason": "prior native failure; no retry or additional inference",
                "usage": None,
            }
        else:
            print(f"Complete task: {entry['task']} / {entry['arm']}", flush=True)
            decision = {}

            def task_bootstrap(root, *, current_task=task, current_decision=decision, **kwargs):
                home = root.parent / "preparation-home"
                home.mkdir()
                with preparation_environment(home, kwargs["cache_dir"]):
                    current_decision.update(
                        prepare_task(
                            root, current_task["prompt"], cwd=root / current_task["scope"], **kwargs
                        )
                    )
                return verify_lock(root)

            def task_profile(root, lock, flags, cwd, current_decision=decision):
                return launch_profile(root, lock, flags, cwd, decision=current_decision)

            def execute(command, prompt, cwd, remaining, current_entry=entry):
                return logged_native(
                    command,
                    prompt,
                    cwd,
                    remaining,
                    evidence / (current_entry["task"] + "-" + current_entry["arm"]),
                )

            args = argparse.Namespace(
                codex=str(codex),
                model=model,
                reasoning_effort="low",
                timeout=timeout,
                work_root=None,
            )
            with (
                patch.object(tasks, "bootstrap", task_bootstrap),
                patch.object(tasks, "launch_profile", task_profile),
                patch.object(tasks, "execute_native", execute),
            ):
                row = tasks.run_one(args, task, entry["arm"], 1, version)
            if decision:
                row["installed_slots"] = row.pop("selected_slots", [])
                row["selected_slots"] = [
                    {"scope": s["scope"], "slot": s["slot"], "source": s["source"]}
                    for s in decision["selected"]
                ]
                row["task_preparation_metrics"] = decision["metrics"]
            stop = bool(
                row.get("returncode")
                or row.get("native_failure_events")
                or row.get("timed_out")
                or row["status"] == "unavailable"
            )
        report["runs"].append(row)
        report["summary"] = tasks.summarize(report["runs"])
        write_json(output, report)
    report["all_attempt_usage"] = {}
    for key in ("input_tokens", "cached_input_tokens", "output_tokens"):
        report["all_attempt_usage"][key] = {}
        for arm in ("baseline", "auto-skills"):
            rows = [r for r in report["runs"] if r["arm"] == arm]
            values = [(r.get("usage") or {}).get(key) for r in rows]
            known = [v for v in values if isinstance(v, int)]
            report["all_attempt_usage"][key][arm] = {
                "planned": len(rows),
                "reported": len(known),
                "total": sum(known) if known else None,
            }
    write_json(output, report)
    return report


def markdown(report):
    lines = [
        "# Automatic skills measurement",
        "",
        LIMITATION,
        "",
        "## Pinned public manifest relevance",
        "",
        "The five language annotations and permitted specialties are stored with the snapshots. Scope and role results include every planned project; missing extracts remain unavailable. Preparation runs offline with isolated inventory. Zero downloads here says nothing about cold network preparation or remote bundle reuse.",
        "",
        "| Project | Scope | Missing capabilities | Irrelevant specialties | First / return seconds | Return cache |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["relevance"]["repositories"]:
        if row["status"] != "measured":
            lines.append(
                f"| {row['repository']} | unavailable | unknown | unknown | unavailable | unavailable |"
            )
            continue
        lines.append(
            f"| [{row['repository']}]({row['manifest_url']}) | {','.join(row['actual_scopes'])} | {', '.join(row['missed_capabilities']) or 'none'} | {', '.join(s['slot'] for s in row['irrelevant_specialties']) or 'none'} | {row['first_preparation_seconds']} / {row['unchanged_return_seconds']} | {row['unchanged_task_cache_hit']} |"
        )
    if report.get("complete_tasks"):
        trials = report["complete_tasks"]
        lines.extend(
            [
                "",
                "## Complete synthetic tasks",
                "",
                f"One repetition, alternating arm order by task; {trials.get('model', 'unavailable')} with existing Codex auth, low reasoning, equal danger-full-access in disposable public fixtures. The wrapper reuses the existing fixture setup, contract checks and independent validators, replacing preparation with offline task-scoped selection. No remote guides or hooks are evaluated. Native logs are private; hashes and native usage are public. Shared authentication/service caches are retained. Every planned row, failure and missing usage is shown.",
                "",
                "| Task | Arm | Status | Validator | Seconds | Input | Cached input | Output |",
                "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in trials["runs"]:
            usage = row.get("usage") or {}
            lines.append(
                f"| {row['task']} | {row['arm']} | {row['status']} | {row.get('after_validation', {}).get('status', 'unavailable')} | {row.get('elapsed_seconds')} | {usage.get('input_tokens')} | {usage.get('cached_input_tokens')} | {usage.get('output_tokens')} |"
            )
        lines.extend(
            [
                "",
                "Input tokens include cached input; the columns must not be added together. Missing reasoning-token fields remain null. Totals in JSON include all reported attempts, including failures. This small single-repetition sample does not support savings claims or a general winner.",
            ]
        )
    else:
        lines.extend(["", "Complete-task inference was not requested in this invocation."])
    lines.extend(
        [
            "",
            "Reproduce: `python tools/measure_automatic_skills.py`; refresh public pins explicitly with `--refresh`; run inference explicitly with `--tasks --model gpt-6.1-sol --codex PATH_TO_NATIVE_CODEX`. The pinned extracts and provenance are in `examples/measurement/`. Refreshing selects new commits and therefore changes the sample.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--tasks", action="store_true")
    parser.add_argument("--model", default="gpt-6.1-sol")
    parser.add_argument("--codex", type=Path, default=DEFAULT_CODEX)
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument(
        "--output", type=Path, default=WORKSPACE / "reports/automatic-skills-measurement.json"
    )
    parser.add_argument("--evidence", type=Path, default=WORKSPACE / "reports/private/measurement")
    args = parser.parse_args(argv)
    if args.refresh:
        refresh()
    report = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "evidence_scope": LIMITATION,
        "platform": platform.system(),
        "python_version": platform.python_version(),
        "relevance": relevance(),
    }
    if args.tasks:
        report["complete_tasks"] = complete_tasks(
            args.codex,
            args.model,
            args.evidence,
            args.output.with_name(args.output.stem + "-tasks.json"),
            args.timeout,
        )
    write_json(args.output, report)
    args.output.with_suffix(".md").write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report["relevance"]["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
