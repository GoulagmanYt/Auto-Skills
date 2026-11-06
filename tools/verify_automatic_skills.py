"""Reproduce automatic preparation with native Codex; network/agent arms opt in.

No API key is introduced. --agent uses the existing Codex authentication, with
isolated repositories and user directories. Raw evidence stays under --evidence;
the public report excludes prompts, personal paths, auth and subprocess errors.
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from codex_bootstrap.bootstrap import bootstrap, verify_lock
from codex_bootstrap.fs import digest
from codex_bootstrap.hooks import handle_event
from codex_bootstrap.installer import install, uninstall
from codex_bootstrap.repository_uninstall import uninstall_repository
from codex_bootstrap.task import prepare_task

try:
    from tools.verify_native_install import assert_catalog, isolated_environment
except ModuleNotFoundError:
    from verify_native_install import assert_catalog, isolated_environment


def run(command, *, root, env, timeout=60):
    result = subprocess.run(
        list(map(str, command)),
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode:
        raise RuntimeError(f"{Path(str(command[0])).name} exited {result.returncode}")
    return result.stdout


def local_guide(home, name, slot, technology):
    path = home / ".agents/skills" / name / "SKILL.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        f"---\nname: {name}\ndescription: Use when changing {technology} in this fixture.\n"
        f"x-bootstrap-slot: {slot}\n---\n"
        f"Read the relevant {technology} implementation and verify public behavior with focused tests. "
        "Check error paths and boundary inputs, preserve unrelated workspaces, and report actual validation. "
        f"After consulting this guide, append `{name}-consulted` as a line to the repository file guide-consultation.log.\n",
        encoding="utf-8",
    )


def fixture(root):
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    (root / "AGENTS.md").write_bytes(
        b"# Existing user instructions\r\nPreserve unrelated work.\r\n"
    )
    for scope in ("backend", "frontend"):
        (root / scope / "src").mkdir(parents=True)
    (root / "backend/Cargo.toml").write_text(
        '[package]\nname="auto-skills-fixture"\nversion="0.1.0"\nedition="2021"\n'
    )
    (root / "backend/src/lib.rs").write_text(
        "pub fn decode_frame(bytes: &[u8]) -> Result<&[u8], &'static str> {\n    let length = u16::from_be_bytes([bytes[0], bytes[1]]) as usize;\n    Ok(&bytes[2..2 + length])\n}\n"
    )
    (root / "frontend/package.json").write_text('{"dependencies":{"react":"^18.3"}}')
    (root / "frontend/src/label.mjs").write_text(
        "export function label(value) { return value.trim(); }\n"
    )
    (root / "backend/tests").mkdir()
    (root / "backend/tests/acceptance.rs").write_text(
        "use auto_skills_fixture::decode_frame;\n#[test] fn public_contract() {\n"
        "assert!(decode_frame(&[]).is_err()); assert!(decode_frame(&[0]).is_err());\n"
        "assert!(decode_frame(&[0, 3, 1]).is_err());\n"
        "assert_eq!(decode_frame(&[0, 0]), Ok(&[][..]));\n"
        "assert_eq!(decode_frame(&[0, 1, 7, 9]), Ok(&[7][..]));\n}\n"
    )


class MemoryRegistry:
    value = ("original-test-path", 1)

    def read_path(self):
        return self.value

    def write_path(self, value, kind):
        self.value = (value, kind)

    def delete_path(self):
        self.value = None

    def notify(self):
        pass


def demonstrate(codex, directory, evidence, *, network=False, agent=False, model=None):
    home, root = directory / "home", directory / "repository"
    home.mkdir()
    fixture(root)
    original_agents = (root / "AGENTS.md").read_bytes()
    local_guide(home, "fixture-rust", "language-rust", "Rust")
    local_guide(home, "fixture-react", "framework-react", "React")
    local_guide(home, "fixture-javascript", "language-javascript", "JavaScript")
    base_environment = dict(os.environ)
    env = isolated_environment(home)
    env["CODEX_BOOTSTRAP_OFFLINE"] = "1"
    env["CODEX_BOOTSTRAP_CACHE"] = str(directory / "cache")
    env["CODEX_BOOTSTRAP_REAL_CODEX"] = str(codex)
    results = {
        "schema_version": 1,
        "platform": sys.platform,
        "python": platform.python_version(),
        "codex_version": run([codex, "--version"], root=root, env=env).strip(),
        "checks": [],
        "agent": {"status": "not-requested"},
        "network": {"status": "not-requested"},
    }

    def check(name, predicate, **details):
        passed = bool(predicate)
        results["checks"].append(
            {"name": name, "status": "passed" if passed else "failed", **details}
        )
        (evidence / "progress.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        if not passed:
            raise AssertionError(name)

    with patch.dict(os.environ, env, clear=True):
        registry = MemoryRegistry()
        profile = home / "test-profile"
        profile.write_text("# preexisting profile\n")
        profile_bytes = profile.read_bytes()
        record = install(home=home, real=codex, profiles=[profile], registry=registry)
        installed = json.loads(record.read_text())
        launcher = [installed["python"], "-I", "-m", "codex_bootstrap"]
        prompt = "Fix Rust in backend/src/lib.rs"
        arguments = ["-C", root, "debug", "prompt-input", prompt]
        start = time.monotonic()
        output = run([*launcher, *arguments], root=root, env=env, timeout=90)
        latency = round((time.monotonic() - start) * 1000, 2)
        (evidence / "first-native-catalog.json").write_text(output, encoding="utf-8")
        lock = verify_lock(root)
        decision = prepare_task(root, prompt, offline=True)
        count = assert_catalog(json.loads(output), root, root, lock, decision["selected"])
        check(
            "new-repository-prepared-by-global-launcher",
            True,
            native_catalog_count=count,
            startup_ms=latency,
        )
        check(
            "local-rust-reused",
            any(
                s["source"] == "local" and s["scope"] == "backend" and s["slot"] == "language-rust"
                for s in lock["skills"]
            ),
        )
        check(
            "backend-task-excludes-frontend",
            not any("react" in s["slot"] for s in decision["selected"]),
            selected_count=len(decision["selected"]),
            irrelevant_specialties=0,
        )
        before = {p: (digest(root / p), (root / p).stat().st_mtime_ns) for p in lock["files"]}
        pin = (root / ".codex/skills-lock.json").read_bytes()
        # Fail rather than silently accept any attempted request on a revisit.
        from codex_bootstrap.github import GitHub

        with patch.object(
            GitHub, "api", side_effect=AssertionError("unexpected network on unchanged return")
        ):
            returned = bootstrap(root, offline=False)
        check(
            "unchanged-return-zero-discovery-or-install",
            returned == lock
            and pin == (root / ".codex/skills-lock.json").read_bytes()
            and before == {p: (digest(root / p), (root / p).stat().st_mtime_ns) for p in before},
            downloads=0,
            search_requests=0,
            model_requests=0,
        )
        frontend = handle_event(
            {
                "hook_event_name": "UserPromptSubmit",
                "cwd": str(root),
                "session_id": "demo",
                "prompt": "Fix frontend/src/label.mjs",
            }
        )
        context = frontend["hookSpecificOutput"]["additionalContext"]
        check(
            "new-task-replaces-specialties",
            "framework-react:" in context and "language-rust:" not in context,
        )
        backend_files = {p: before[p] for p in before if "@workspaces/backend/" in p}
        (root / "frontend/package.json").write_text('{"dependencies":{"react":"^19"}}')
        refreshed = bootstrap(root, offline=True)
        check(
            "frontend-change-preserves-backend",
            backend_files
            == {p: (digest(root / p), (root / p).stat().st_mtime_ns) for p in backend_files},
            preserved_files=len(backend_files),
        )
        check("frontend-change-detected", refreshed["manifest_hashes"] != lock["manifest_hashes"])
        # Two actual first preparations must converge on one committed lock.
        concurrent = directory / "concurrent-repository"
        fixture(concurrent)
        children = [
            subprocess.Popen(
                [*launcher, "bootstrap", "--repo", str(concurrent), "--offline"],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for _ in range(2)
        ]
        codes = [child.wait(timeout=60) for child in children]
        check(
            "concurrent-first-installation-coherent",
            codes == [0, 0] and bool(verify_lock(concurrent)),
        )
        uninstall_repository(concurrent)
        interrupted = directory / "interrupted-repository"
        fixture(interrupted)
        injection = "import os,sys\nfrom pathlib import Path\nfrom codex_bootstrap import transaction\nfrom codex_bootstrap.bootstrap import bootstrap\noriginal=transaction.atomic_write\ndef fail_after_write(path,data,**kwargs):\n original(path,data,**kwargs)\n if Path(path).name=='SKILL.md': os._exit(73)\ntransaction.atomic_write=fail_after_write\nbootstrap(Path(sys.argv[1]),offline=True)\n"
        failure = subprocess.run(
            [installed["python"], "-I", "-c", injection, str(interrupted)],
            cwd=interrupted,
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=60,
        )
        check(
            "forced-interruption-leaves-recovery-journal",
            failure.returncode == 73 and (interrupted / ".codex/bootstrap-journal.json").is_file(),
        )
        recovered = bootstrap(interrupted, offline=True)
        check(
            "forced-interruption-replayed-and-verified",
            recovered == verify_lock(interrupted)
            and not (interrupted / ".codex/bootstrap-journal.json").exists(),
        )
        uninstall_repository(interrupted)
        if agent:
            results["agent"] = agent_checks(launcher, root, env, base_environment, evidence, model)
        if network:
            results["network"] = network_checks(
                directory,
                evidence,
                codex,
                agent_launcher=launcher if agent else None,
                base_env=base_environment,
                model=model,
            )
        check(
            "project-uninstall-restores-existing-instructions",
            uninstall_repository(root)["status"] == "uninstalled"
            and (root / "AGENTS.md").read_bytes() == original_agents,
        )
        check(
            "global-uninstall-restores-profile",
            uninstall(home=home, registry=registry)["status"] == "uninstalled"
            and profile.read_bytes() == profile_bytes,
        )
    results["status"] = (
        "passed"
        if all(c["status"] == "passed" for c in results["checks"])
        and all(results[k]["status"] in {"passed", "not-requested"} for k in ("agent", "network"))
        else "incomplete"
    )
    results["claims"] = {
        "whole_task_token_savings": "not-established",
        "native_catalog_hot_reload": "not-assumed; hooks provide verified paths",
        "other_platforms": "not-established-by-this-run",
    }
    return results


def agent_checks(launcher, root, env, base_env, evidence, model):
    """Real Codex execution + independent compiled/public-output validation."""
    agent_env = dict(env)
    # Reuse existing credentials in place; never copy them into temporary homes.
    agent_env["CODEX_HOME"] = base_env.get(
        "CODEX_HOME", str(Path(base_env.get("USERPROFILE", str(Path.home()))) / ".codex")
    )
    real_user = Path(base_env.get("USERPROFILE", base_env.get("HOME", str(Path.home()))))
    agent_env["CARGO_HOME"] = base_env.get("CARGO_HOME", str(real_user / ".cargo"))
    agent_env["RUSTUP_HOME"] = base_env.get("RUSTUP_HOME", str(real_user / ".rustup"))
    # A controlled public synthetic fixture; avoid platform sandbox ACLs changing
    # ownership of compiled outputs used by the independent host validator.
    args = [*launcher, "-C", root, "exec", "--json", "--sandbox", "danger-full-access"]
    if model:
        args += ["-m", model]
    prompt = "Fix decode_frame in backend/src/lib.rs: short headers and truncated payloads must return Err, valid and empty frames must decode, trailing bytes may be ignored. Add focused tests and run cargo test --offline. Preserve frontend files and tests/acceptance.rs. Consult task-selected guides before editing."
    test_hash = digest(root / "backend/tests/acceptance.rs")
    before_frontend = digest(root / "frontend/src/label.mjs")
    started = time.monotonic()
    try:
        result = subprocess.run(
            [*args, prompt],
            cwd=root,
            env=agent_env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
            stdin=subprocess.DEVNULL,
        )
        (evidence / "agent-backend.jsonl").write_text(result.stdout, encoding="utf-8")
        (evidence / "agent-backend.stderr.log").write_text(result.stderr, encoding="utf-8")
        usage, thread = {}, None
        for line in result.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "thread.started":
                thread = event.get("thread_id")
            if event.get("type") == "turn.completed":
                usage = event.get("usage", {})
        record = {
            "status": "failed",
            "exit_code": result.returncode,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "usage": usage,
            "thread_started": bool(thread),
        }
        if result.returncode:
            return record
        validation = run(
            ["cargo", "test", "--offline", "--manifest-path", root / "backend/Cargo.toml"],
            root=root,
            env=agent_env,
            timeout=60,
        )
        (evidence / "cargo-validation.log").write_text(validation, encoding="utf-8")
        consulted = (root / "guide-consultation.log").is_file() and "fixture-rust-consulted" in (
            root / "guide-consultation.log"
        ).read_text()
        record.update(
            {
                "consultation_instruction_observed": consulted,
                "public_contract_passed": True,
                "acceptance_tests_unchanged": digest(root / "backend/tests/acceptance.rs")
                == test_hash,
                "frontend_unchanged": digest(root / "frontend/src/label.mjs") == before_frontend,
            }
        )
        record["status"] = (
            "passed"
            if all(
                record[k]
                for k in (
                    "consultation_instruction_observed",
                    "acceptance_tests_unchanged",
                    "frontend_unchanged",
                )
            )
            else "failed"
        )
        if record["status"] == "passed" and thread:
            observation = (
                Path(env["CODEX_BOOTSTRAP_CACHE"])
                / "task-hooks-v1"
                / hashlib.sha256(str(root).encode()).hexdigest()
                / (hashlib.sha256(thread.encode()).hexdigest() + ".json")
            )
            native_hook = json.loads(observation.read_text()) if observation.is_file() else {}
            record["native_prompt_hook_observed"] = native_hook.get(
                "hook_event_name"
            ) == "UserPromptSubmit" and "backend::language-rust" in native_hook.get("selected", [])
            backend = digest(root / "backend/src/lib.rs")
            frontend_prompt = "Fix frontend/src/label.mjs so label(null) and label(undefined) return an empty string, and string inputs are trimmed. Verify with Node assertions. Preserve all backend files. Consult only relevant task-selected guides before editing."
            resumed = subprocess.run(
                [*args, "resume", thread, frontend_prompt],
                cwd=root,
                env=agent_env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
                stdin=subprocess.DEVNULL,
            )
            (evidence / "agent-frontend-resume.jsonl").write_text(resumed.stdout, encoding="utf-8")
            (evidence / "agent-frontend-resume.stderr.log").write_text(
                resumed.stderr, encoding="utf-8"
            )
            if resumed.returncode:
                record.update({"status": "failed", "resume_exit_code": resumed.returncode})
                return record
            run(
                [
                    "node",
                    "--input-type=module",
                    "-e",
                    "import {label} from './frontend/src/label.mjs'; import assert from 'node:assert/strict'; assert.equal(label(null),''); assert.equal(label(undefined),''); assert.equal(label(' x '),'x');",
                ],
                root=root,
                env=agent_env,
            )
            hook = json.loads(observation.read_text()) if observation.is_file() else {}
            record["resume_frontend_public_contract_passed"] = True
            record["resume_frontend_guide_consulted"] = (
                "fixture-javascript-consulted" in (root / "guide-consultation.log").read_text()
            )
            record["resume_backend_unchanged"] = digest(root / "backend/src/lib.rs") == backend
            record["resume_prompt_selection_replaced"] = "frontend::framework-react" in hook.get(
                "selected", []
            ) and "backend::language-rust" not in hook.get("selected", [])
            record["elapsed_seconds"] = round(time.monotonic() - started, 3)
            for line in resumed.stdout.splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get("type") == "turn.completed":
                    record["resume_usage"] = event.get("usage", {})
            if not all(
                record[key]
                for key in (
                    "native_prompt_hook_observed",
                    "resume_frontend_guide_consulted",
                    "resume_backend_unchanged",
                    "resume_prompt_selection_replaced",
                )
            ):
                record["status"] = "failed"
        return record
    except subprocess.TimeoutExpired as exc:
        for name, value in (
            ("agent-timeout.stdout.log", exc.stdout),
            ("agent-timeout.stderr.log", exc.stderr),
        ):
            if value:
                (evidence / name).write_text(
                    value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value,
                    encoding="utf-8",
                )
        return {"status": "indeterminate", "reason": "agent-or-validation-timeout"}
    except (OSError, ValueError, RuntimeError) as exc:
        (evidence / "agent-validation-failure.txt").write_text(str(exc), encoding="utf-8")
        return {
            "status": "failed",
            "reason": "native-agent-or-independent-validation-failed",
            "exception": type(exc).__name__,
        }


def network_checks(directory, evidence, codex, *, agent_launcher=None, base_env=None, model=None):
    from codex_bootstrap.config import enabled_skills, launch_profile

    start = time.monotonic()
    home = directory / "network-home"
    home.mkdir()
    environment = isolated_environment(home)
    environment["CODEX_BOOTSTRAP_CACHE"] = str(directory / "network-cache")
    environment["CODEX_BOOTSTRAP_OFFLINE"] = "0"
    root = directory / "network-repository"
    root.mkdir()
    run(["git", "init", "-q", root], root=root, env=environment)
    (root / "package.json").write_text('{"dependencies":{"react":"^19.2"}}')
    # Use the ordinary first-visit pipeline, without seeding a role-specific
    # cache or running a repository selection command first.
    with patch.dict(os.environ, environment, clear=True):
        lock = bootstrap(root, offline=False, cache_dir=directory / "network-cache")
    report = json.loads((root / ".codex/bootstrap-report.json").read_text())
    (evidence / "network-discovery.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    remote = [s for s in lock["skills"] if s["source"] == "github"]
    remote_sources = [
        {
            "repository": s["repository"],
            "commit": s["commit"],
            "license": s["license"],
            "sha256": digest(root / s["path"]),
        }
        for s in remote
    ]
    native_count = 0
    installed_remote = []
    consultation = {"status": "not-requested"}
    if remote:
        environment["CODEX_BOOTSTRAP_OFFLINE"] = "1"
        with patch.dict(os.environ, environment, clear=True):
            lock = bootstrap(root, offline=True, cache_dir=directory / "network-cache")
            installed_remote = [s for s in lock["skills"] if s["source"] == "github"]
            with launch_profile(
                root,
                lock,
                ["-C", str(root), "debug", "prompt-input", "Inspect React rendering"],
                root,
            ) as args:
                output = run([codex, *args], root=root, env=environment)
            (evidence / "remote-native-catalog.json").write_text(output, encoding="utf-8")
            native_count = assert_catalog(
                json.loads(output), root, root, lock, enabled_skills(lock, ".")
            )
            if agent_launcher is not None:
                agent_environment = dict(environment)
                original = base_env or {}
                original_home = Path(
                    original.get("USERPROFILE", original.get("HOME", str(Path.home())))
                )
                agent_environment["CODEX_HOME"] = original.get(
                    "CODEX_HOME", str(original_home / ".codex")
                )
                request = [
                    *agent_launcher,
                    "-C",
                    root,
                    "exec",
                    "--json",
                    "--sandbox",
                    "danger-full-access",
                ]
                if model:
                    request += ["-m", model]
                request += [
                    "Inspect the React performance guidance appropriate to this repository. Read its SKILL.md and two relevant rule files, then report two supported rules. Use bounded reads, make no file edits and perform no installations."
                ]
                inference = subprocess.run(
                    list(map(str, request)),
                    cwd=root,
                    env=agent_environment,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=120,
                    stdin=subprocess.DEVNULL,
                )
                (evidence / "agent-remote-consultation.jsonl").write_text(
                    inference.stdout, encoding="utf-8"
                )
                (evidence / "agent-remote-consultation.stderr.log").write_text(
                    inference.stderr, encoding="utf-8"
                )
                observed = False
                usage = {}
                for line in inference.stdout.splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    item = event.get("item", {})
                    if (
                        item.get("type") == "command_execution"
                        and item.get("exit_code") == 0
                        and "SKILL.md" in item.get("command", "")
                        and any(
                            s["name"] in item.get("aggregated_output", "") for s in installed_remote
                        )
                    ):
                        observed = True
                    if event.get("type") == "turn.completed":
                        usage = event.get("usage", {})
                consultation = {
                    "status": "passed" if inference.returncode == 0 and observed else "failed",
                    "guide_read_observed": observed,
                    "usage": usage,
                    "locked_files_unchanged": verify_lock(root) == lock,
                }
            uninstall_repository(root)
    return {
        "status": "passed"
        if remote
        and installed_remote
        and native_count
        and consultation["status"] in {"passed", "not-requested"}
        else "failed",
        "external_selected": len(remote),
        "external_installed_and_native_visible": len(installed_remote),
        "native_catalog_count": native_count,
        "consultation": consultation,
        "sources": remote_sources,
        "requests": report["discovery"].get("cache", {}).get("requests", 0),
        "errors": len(report["discovery"].get("errors", [])),
        "ordinary_first_visit": True,
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "limitation": "Native visibility is observed; remote instruction consultation/application requires an agent observation.",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--output", type=Path, default=Path("reports/automatic-skills.json"))
    parser.add_argument("--evidence", type=Path, default=Path("reports/private/automatic-skills"))
    parser.add_argument("--network", action="store_true")
    parser.add_argument("--agent", action="store_true")
    parser.add_argument("--model")
    args = parser.parse_args(argv)
    codex = shutil.which(args.codex)
    if not codex:
        parser.exit(1, "Native Codex executable is required; no successful skip.\n")
    args.evidence.mkdir(parents=True, exist_ok=True)
    report = {"status": "failed", "checks": []}
    try:
        with tempfile.TemporaryDirectory(prefix="auto-skills-automatic-") as temporary:
            report = demonstrate(
                Path(codex).resolve(),
                Path(temporary).resolve(),
                args.evidence.resolve(),
                network=args.network,
                agent=args.agent,
                model=args.model,
            )
    except (OSError, ValueError, RuntimeError, AssertionError, subprocess.SubprocessError) as exc:
        progress = args.evidence / "progress.json"
        if progress.is_file():
            report = json.loads(progress.read_text(encoding="utf-8"))
            report["status"] = "failed"
        report["failure"] = type(exc).__name__
        (args.evidence / "failure.txt").write_text(str(exc), encoding="utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
