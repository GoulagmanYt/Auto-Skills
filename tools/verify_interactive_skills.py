"""Observe four actual turns in one native app-server process and thread.

Direct app-server is a controlled integration surface here: preparation and the
same launch profile/hooks used by the wrapper are supplied explicitly. This is
not a claim that an unwrapped app-server launch is automatically integrated.
Credentials remain in the existing CODEX_HOME. Raw RPC evidence is private.
"""

import argparse
import hashlib
import json
import os
import platform
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from pathlib import Path
from unittest.mock import patch

from codex_bootstrap.bootstrap import bootstrap, verify_lock
from codex_bootstrap.config import launch_overrides
from codex_bootstrap.fs import digest
from codex_bootstrap.native_hooks import hook_overrides
from codex_bootstrap.task import prepare_task

try:
    from tools.verify_automatic_skills import fixture, local_guide
    from tools.verify_native_install import isolated_environment
except ModuleNotFoundError:
    from verify_automatic_skills import fixture, local_guide
    from verify_native_install import isolated_environment


class RpcClient:
    """Bounded JSONL RPC client; retains notifications received before replies."""

    def __init__(self, command, *, cwd, env, evidence):
        self.log = (evidence / "interactive-rpc.jsonl").open("w", encoding="utf-8")
        self.errors = (evidence / "interactive-stderr.log").open("w", encoding="utf-8")
        self.process = subprocess.Popen(
            list(map(str, command)),
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.errors,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        self.events = queue.Queue()
        self.pending = []
        self.sequence = 0
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(8_000_001)
                if not line:
                    raise EOFError("native app-server stdout closed")
                if len(line) > 8_000_000:
                    raise ValueError("native RPC event exceeded byte budget")
                self.events.put(json.loads(line))
        except Exception as exc:
            self.events.put(exc)

    def send(self, value):
        self.log.write(json.dumps({"direction": "sent", "message": value}) + "\n")
        self.log.flush()
        self.process.stdin.write(json.dumps(value) + "\n")
        self.process.stdin.flush()

    def receive(self, deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("native RPC deadline exceeded")
        try:
            event = self.events.get(timeout=remaining)
        except queue.Empty as exc:
            raise TimeoutError("native RPC deadline exceeded") from exc
        if isinstance(event, Exception):
            raise event
        self.log.write(json.dumps({"direction": "received", "message": event}) + "\n")
        self.log.flush()
        if "method" in event and "id" in event:
            # Never grant additional rights if a fixture unexpectedly requests them.
            self.send(
                {
                    "id": event["id"],
                    "error": {
                        "code": -32601,
                        "message": "Verifier does not approve server requests",
                    },
                }
            )
            raise RuntimeError("unexpected server request: " + event["method"])
        return event

    def request(self, method, params, *, timeout=30):
        self.sequence += 1
        identifier = self.sequence
        self.send({"id": identifier, "method": method, "params": params})
        deadline = time.monotonic() + timeout
        while True:
            event = self.receive(deadline)
            if event.get("id") == identifier:
                if "error" in event:
                    raise RuntimeError(
                        "native RPC rejected " + method + ": " + json.dumps(event["error"])
                    )
                return event["result"]
            self.pending.append(event)

    def turn(self, thread, prompt, *, timeout=240):
        started = time.monotonic()
        result = self.request(
            "turn/start",
            {"threadId": thread, "input": [{"type": "text", "text": prompt}], "effort": "low"},
            timeout=timeout,
        )
        turn = result["turn"]["id"]
        observed = []
        deadline = started + timeout
        while True:
            event = self.pending.pop(0) if self.pending else self.receive(deadline)
            params = event.get("params", {})
            if params.get("threadId") == thread:
                observed.append(event)
            if (
                event.get("method") == "turn/completed"
                and params.get("threadId") == thread
                and params.get("turn", {}).get("id") == turn
            ):
                return params["turn"], observed, round(time.monotonic() - started, 3)

    def close(self):
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=10)
        self.reader.join(timeout=2)
        self.process.stdout.close()
        self.log.close()
        self.errors.close()


def completed_commands(events):
    return [
        event["params"]["item"]
        for event in events
        if event.get("method") == "item/completed"
        and event.get("params", {}).get("item", {}).get("type") == "commandExecution"
    ]


def observed_reads(events, lock):
    """Require completed command evidence of a concrete guide read, not a mention.

    Match the guide's on-disk name/path in a read command. Output must include
    frontmatter from an actual SKILL.md. Listing paths or echoed agent text is
    insufficient. Markers are a separate controlled-obedience measurement.
    """
    found = set()
    for command in completed_commands(events):
        text = command.get("command", "").replace("\\", "/")
        output = command.get("aggregatedOutput", "")
        if command.get("exitCode") != 0 or "SKILL.md" not in text or "name:" not in output:
            continue
        if not any(
            word in text.lower() for word in ("get-content", "cat ", "read_text", "sed ", "type ")
        ):
            continue
        for entry in lock["skills"]:
            if (
                any(entry[key].replace("\\", "/") in text for key in ("path", "discovery_path"))
                or f"name: {entry['name']}\n" in output
            ):
                found.add(entry.get("scope", ".") + "::" + entry["slot"])
    return sorted(found)


def hook_snapshot(cache, root, thread):
    suffix = Path(hashlib.sha256(str(root).encode()).hexdigest()) / (
        hashlib.sha256(thread.encode()).hexdigest() + ".json"
    )
    hook = cache / "task-hooks-v1" / suffix
    state = cache / "task-state-v1" / suffix
    return (
        json.loads(hook.read_text()) if hook.is_file() else {},
        json.loads(state.read_text()) if state.is_file() else {},
    )


def validate(command, *, root, env, evidence, name):
    result = subprocess.run(
        list(map(str, command)),
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    (evidence / ("interactive-" + name + ".log")).write_text(
        result.stdout + result.stderr, encoding="utf-8"
    )
    return result.returncode == 0


def demonstrate(codex, directory, evidence, *, model, timeout=240):
    home, root, cache = directory / "home", directory / "repository", directory / "cache"
    home.mkdir()
    fixture(root)
    for name, slot, technology in (
        ("fixture-rust", "language-rust", "Rust"),
        ("fixture-react", "framework-react", "React"),
        ("fixture-javascript", "language-javascript", "JavaScript"),
    ):
        local_guide(home, name, slot, technology)
    # Available locally but deliberately absent from initial lock/catalog.
    portable = home / ".agents/skills/fixture-browser/SKILL.md"
    portable.parent.mkdir(parents=True)
    portable.write_text(
        "---\nname: fixture-browser\ndescription: Use for portable user-facing behavior acceptance checks.\nx-bootstrap-slot: e2e-testing\n---\nRead public behavior and independently check null, empty and whitespace inputs. Append `fixture-browser-consulted` to guide-consultation.log after reading this guide. For this fixture Node assertions exercise the public label contract; do not claim real browser coverage.\n",
        encoding="utf-8",
    )
    base = dict(os.environ)
    env = isolated_environment(home)
    real_user = Path(base.get("USERPROFILE", base.get("HOME", str(Path.home()))))
    env.update(
        {
            "CODEX_HOME": base.get("CODEX_HOME", str(real_user / ".codex")),
            "CODEX_BOOTSTRAP_CACHE": str(cache),
            "CARGO_HOME": base.get("CARGO_HOME", str(real_user / ".cargo")),
            "RUSTUP_HOME": base.get("RUSTUP_HOME", str(real_user / ".rustup")),
        }
    )
    report = {
        "schema_version": 1,
        "status": "failed",
        "platform": sys.platform,
        "python": platform.python_version(),
        "model": model,
        "turns": [],
        "checks": [],
        "limits": [
            "Controlled direct app-server launch with explicit manager preparation/profile/hooks; not automatic integration of arbitrary app-server clients.",
            "One synthetic offline local capability acquisition; no claim of native hot catalog reload or actual browser coverage.",
            "Same native process/thread; earlier guide context remains in thread history, so exclusion measures new selection/reads only.",
            "Controlled guide markers and transcript reads establish consultation, not causal superiority or token savings.",
        ],
    }
    started = time.monotonic()
    client = None
    try:
        with patch.dict(os.environ, env, clear=True):
            # Inventory must not import the real user's plugin/skill catalog.
            # Only HOME is isolated; authentication stays at its original path.
            # Native strict mode separately disables global catalog entries.
            lock = bootstrap(root, offline=True)
            first = "Fix decode_frame in backend/src/lib.rs so short headers and truncated payloads return Err, valid and empty frames decode, trailing bytes may be ignored. Preserve backend/tests/acceptance.rs and frontend files. Add tests and run cargo test --offline. Read relevant selected guides before editing."
            decision = prepare_task(root, first, offline=True)
            hook_args = hook_overrides([str(codex)], root)
            report["checks"].append(
                {
                    "name": "exact-native-hook-trust-configured",
                    "passed": bool(hook_args)
                    and any("hooks.state=" in arg for arg in hook_args)
                    and not any("bypass" in arg for arg in hook_args),
                }
            )
            initial_missing = not any(entry["slot"] == "e2e-testing" for entry in lock["skills"])
            report["checks"].append(
                {"name": "additional-capability-initially-absent", "passed": initial_missing}
            )
            # app-server rejects --profile; its documented thread config object
            # accepts the same flattened overrides without a Windows argv limit.
            overrides = launch_overrides(root, lock, decision=decision)
            configuration = {
                value.split("=", 1)[0]: tomllib.loads("value=" + value.split("=", 1)[1])["value"]
                for value in overrides[1::2]
            }
            client = RpcClient(
                [codex, *hook_args, "app-server"], cwd=root, env=env, evidence=evidence
            )
            pid = client.process.pid
            initialization = client.request(
                "initialize",
                {"clientInfo": {"name": "auto-skills-sustained-verifier", "version": "1"}},
            )
            report["codex_version"] = initialization.get("userAgent", "unknown")
            client.send({"method": "initialized"})
            thread = client.request(
                "thread/start",
                {
                    "cwd": str(root),
                    "model": model,
                    "approvalPolicy": "never",
                    "sandbox": "danger-full-access",
                    "config": configuration,
                },
            )["thread"]["id"]
            acceptance = digest(root / "backend/tests/acceptance.rs")
            frontend = digest(root / "frontend/src/label.mjs")
            prompts = [
                first,
                "Fix frontend/src/label.mjs so label(null) and label(undefined) return an empty string, string inputs are trimmed. Verify with Node assertions. Preserve backend files. Read the new task-selected relevant guides before editing; prior backend guides do not apply to this turn.",
                "For frontend/src/label.mjs acquire the missing portable e2e-testing capability through the task manager using a justified proposal for frontend and frontend/src/label.mjs. Use the existing local guide, stay offline, and do not install packages. Write capability-proposal.json with schema_version=1, scopes=['frontend'], files=['frontend/src/label.mjs'], capabilities=['e2e-testing'], reasons={'e2e-testing':'Independently validate the public user-facing label contract across empty and whitespace inputs'}. Invoke the existing Python with -I -m codex_bootstrap task --repo . --proposal capability-proposal.json --json. Read the newly returned verified guide path, then create frontend/acceptance.mjs using node:assert/strict to check label(null), label(undefined), label(''), label('  ') and label(' x '). Run it with Node. Preserve backend files. Do not claim browser coverage.",
                "Return to backend/src/lib.rs. Add a public encode_frame(payload: &[u8]) -> Result<Vec<u8>, &'static str> matching decode_frame's big-endian u16 header, rejecting payloads longer than 65535 bytes. Add focused tests and run cargo test --offline. Preserve frontend files and backend/tests/acceptance.rs. Read the current relevant selected backend guides; frontend and e2e guides are irrelevant now.",
            ]
            for index, prompt in enumerate(prompts):
                before_lock = verify_lock(root)
                expected_scope = "backend" if index in {0, 3} else "frontend"
                sibling = "frontend" if expected_scope == "backend" else "backend"
                before_marker = (
                    (root / "guide-consultation.log").read_text()
                    if (root / "guide-consultation.log").is_file()
                    else ""
                )
                backend_before = digest(root / "backend/src/lib.rs")
                frontend_before = {
                    p: digest(root / p)
                    for p in ("frontend/src/label.mjs", "frontend/acceptance.mjs")
                    if (root / p).is_file()
                }
                # Preserve submitted attempts even if RPC, integrity or the
                # independent validator raises before a complete row exists.
                report["turns"].append(
                    {
                        "turn": index + 1,
                        "scope": expected_scope,
                        "native_status": "unknown",
                        "status": "indeterminate",
                        "independent_task_check_passed": False,
                        "selection_relevant": False,
                        "new_guide_reads": [],
                    }
                )
                turn, events, elapsed = client.turn(thread, prompt, timeout=timeout)
                report["turns"][-1].update(
                    {"native_status": turn.get("status"), "elapsed_seconds": elapsed}
                )
                (evidence / f"interactive-turn-{index + 1}.json").write_text(
                    json.dumps({"turn": turn, "events": events}, indent=2), encoding="utf-8"
                )
                hook, state = hook_snapshot(cache, root, thread)
                current = verify_lock(root)
                reads = observed_reads(events, current)
                marker = (
                    (root / "guide-consultation.log").read_text()
                    if (root / "guide-consultation.log").is_file()
                    else ""
                )
                new_markers = (
                    marker[len(before_marker) :].splitlines()
                    if marker.startswith(before_marker)
                    else []
                )
                selected = hook.get("selected", [])
                hook_ok = (
                    hook.get("hook_event_name") == "UserPromptSubmit"
                    and hook.get("prompt_sha256") == hashlib.sha256(prompt.encode()).hexdigest()
                )
                selection_ok = any(
                    key.startswith(expected_scope + "::") for key in selected
                ) and not any(key.startswith(sibling + "::") for key in selected)
                reads_ok = any(key.startswith(expected_scope + "::") for key in reads) and not any(
                    key.startswith(sibling + "::") for key in reads
                )
                independent = (
                    validate(
                        [
                            "cargo",
                            "test",
                            "--offline",
                            "--manifest-path",
                            root / "backend/Cargo.toml",
                        ],
                        root=root,
                        env=env,
                        evidence=evidence,
                        name=f"turn-{index + 1}-cargo",
                    )
                    if index in {0, 3}
                    else validate(
                        [
                            "node",
                            "--input-type=module",
                            "-e",
                            "import {label} from './frontend/src/label.mjs'; import assert from 'node:assert/strict'; for (const input of [null,undefined,'','  ']) assert.equal(label(input),''); assert.equal(label(' x '),'x');",
                        ],
                        root=root,
                        env=env,
                        evidence=evidence,
                        name=f"turn-{index + 1}-node",
                    )
                )
                preserved = digest(root / "backend/tests/acceptance.rs") == acceptance and (
                    digest(root / "backend/src/lib.rs") == backend_before
                    if expected_scope == "frontend"
                    else all(digest(root / p) == value for p, value in frontend_before.items())
                )
                if index == 0:
                    preserved = preserved and digest(root / "frontend/src/label.mjs") == frontend
                if index == 2:
                    extra = [entry for entry in current["skills"] if entry["slot"] == "e2e-testing"]
                    proposal = (
                        json.loads((root / "capability-proposal.json").read_text())
                        if (root / "capability-proposal.json").is_file()
                        else {}
                    )
                    capability_ok = (
                        bool(extra)
                        and extra[0]["source"] == "local"
                        and "e2e-testing"
                        in current.get("requested_capabilities", {}).get("frontend", [])
                        and "frontend::e2e-testing" in reads
                        and "fixture-browser-consulted" in new_markers
                        and bool(proposal.get("reasons", {}).get("e2e-testing"))
                        and state.get("method") == "validated-agent-proposal"
                    )
                    independent = independent and validate(
                        ["node", root / "frontend/acceptance.mjs"],
                        root=root,
                        env=env,
                        evidence=evidence,
                        name="portable-acceptance",
                    )
                    report["checks"].append(
                        {
                            "name": "additional-capability-installed-and-read-in-same-process",
                            "passed": capability_ok,
                            "lock_skill_count_before": len(before_lock["skills"]),
                            "lock_skill_count_after": len(current["skills"]),
                        }
                    )
                if index == 3:
                    (root / "backend/tests/encoder_acceptance.rs").write_text(
                        "use auto_skills_fixture::{decode_frame,encode_frame};\n#[test] fn encoder_contract() { for p in [vec![],vec![7],vec![3;65535]] { let encoded=encode_frame(&p).unwrap(); assert_eq!(encoded.len(),p.len()+2); assert_eq!(decode_frame(&encoded).unwrap(),p); } assert!(encode_frame(&vec![0;65536]).is_err()); }\n"
                    )
                    independent = independent and validate(
                        [
                            "cargo",
                            "test",
                            "--offline",
                            "--manifest-path",
                            root / "backend/Cargo.toml",
                        ],
                        root=root,
                        env=env,
                        evidence=evidence,
                        name="encoder-acceptance",
                    )
                marker_name = (
                    "fixture-rust-consulted"
                    if expected_scope == "backend"
                    else "fixture-browser-consulted"
                    if index == 2
                    else "fixture-javascript-consulted"
                )
                row = {
                    "turn": index + 1,
                    "scope": expected_scope,
                    "native_status": turn.get("status"),
                    "elapsed_seconds": elapsed,
                    "same_process_alive": client.process.poll() is None
                    and client.process.pid == pid,
                    "native_prompt_hook_observed": hook_ok,
                    "selection_relevant": selection_ok,
                    "selected": selected,
                    "new_guide_reads": reads,
                    "reads_relevant": reads_ok,
                    "consultation_marker_observed": marker_name in new_markers,
                    "independent_task_check_passed": independent,
                    "unrelated_files_preserved": preserved,
                    "selection_latency_ms": state.get("metrics", {}).get("latency_ms"),
                }
                row["status"] = (
                    "passed"
                    if turn.get("status") == "completed"
                    and all(
                        row[key]
                        for key in (
                            "same_process_alive",
                            "native_prompt_hook_observed",
                            "selection_relevant",
                            "reads_relevant",
                            "consultation_marker_observed",
                            "independent_task_check_passed",
                            "unrelated_files_preserved",
                        )
                    )
                    else "failed"
                )
                report["turns"][-1] = row
                print(f"Interactive turn {index + 1}/4: {row['status']} ({elapsed}s)", flush=True)
                (evidence / "interactive-progress.json").write_text(
                    json.dumps(report, indent=2), encoding="utf-8"
                )
                if turn.get("status") != "completed":
                    report["stopped_reason"] = "native turn failed; remaining turns not attempted"
                    break
            report["checks"].append(
                {"name": "one-thread-four-distinct-turns", "passed": len(report["turns"]) == 4}
            )
            report["checks"].append(
                {
                    "name": "capability-retained-after-backend-return",
                    "passed": "e2e-testing"
                    in verify_lock(root).get("requested_capabilities", {}).get("frontend", []),
                }
            )
            report["status"] = (
                "passed"
                if all(row["status"] == "passed" for row in report["turns"])
                and all(check["passed"] for check in report["checks"])
                else "failed"
            )
    except Exception as exc:
        (evidence / "interactive-failure.txt").write_text(repr(exc), encoding="utf-8")
        report["failure_type"] = type(exc).__name__
    finally:
        if client:
            client.close()
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        report["metrics"] = {
            "planned_turns": 4,
            "attempted_turns": len(report["turns"]),
            "completed_turns": sum(row["native_status"] == "completed" for row in report["turns"]),
            "task_checks_passed": sum(
                row["independent_task_check_passed"] for row in report["turns"]
            ),
            "relevant_selections": sum(row["selection_relevant"] for row in report["turns"]),
            "irrelevant_sibling_new_reads": sum(
                any(
                    key.startswith(("frontend" if row["scope"] == "backend" else "backend") + "::")
                    for key in row["new_guide_reads"]
                )
                for row in report["turns"]
            ),
        }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", type=Path, default=shutil.which("codex"))
    parser.add_argument("--model", default="gpt-6.1-sol")
    parser.add_argument(
        "--output", type=Path, default=Path("reports/automatic-skills-interactive.json")
    )
    parser.add_argument("--evidence", type=Path, default=Path("reports/private/interactive"))
    parser.add_argument("--turn-timeout", type=int, default=240)
    args = parser.parse_args()
    if not args.codex or not args.codex.is_file():
        parser.error("--codex must name the native Codex executable")
    args.evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="auto-skills-interactive-", ignore_cleanup_errors=True
    ) as temporary:
        report = demonstrate(
            args.codex.resolve(),
            Path(temporary),
            args.evidence.resolve(),
            model=args.model,
            timeout=args.turn_timeout,
        )
        # Keep synthetic source artifacts with raw evidence, never authentication.
        shutil.copytree(
            Path(temporary) / "repository",
            args.evidence / "interactive-fixture",
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("target", ".git"),
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"status": report["status"], "turns": len(report["turns"]), "report": str(args.output)}
        )
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
