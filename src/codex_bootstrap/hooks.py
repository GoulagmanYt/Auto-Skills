"""Codex lifecycle adapter: bounded JSON stdin, verified task context on stdout."""

import json
import os
import sys
from pathlib import Path

from .bootstrap import git_root
from .decision_state import read_decision
from .fs import atomic_write, json_text
from .github import default_cache_dir
from .task import prepare_task, repository_identity, task_context


def handle_event(event):
    import hashlib

    if isinstance(event, dict) and event.get("hook_event_name") == "PostToolUse":
        # Observability is advisory: it never changes a tool result or user turn.
        try:
            from .observations import record_tool_event

            root = git_root(Path(event.get("cwd", str(Path.cwd()))))
            if root is not None:
                record_tool_event(root, event)
        except (OSError, ValueError, TypeError, KeyError):
            pass
        return {}
    if not isinstance(event, dict) or event.get("hook_event_name") not in {
        "SessionStart",
        "UserPromptSubmit",
    }:
        return {}
    cwd = Path(event.get("cwd", str(Path.cwd()))).resolve()
    root = git_root(cwd)
    if root is None:
        return {}
    session = str(event.get("session_id", "launch"))[:256]
    proposal = None
    if event["hook_event_name"] == "SessionStart" and event.get("source") in {
        "resume",
        "compact",
        "fork",
    }:
        state = (
            default_cache_dir()
            / "task-state-v1"
            / hashlib.sha256(str(root).encode()).hexdigest()
            / (hashlib.sha256(session.encode()).hexdigest() + ".json")
        )
        previous = read_decision(state)
        if previous is not None:
            try:
                if previous.get("repository") == repository_identity(root):
                    proposal = {
                        "schema_version": 1,
                        "scopes": previous["scopes"],
                        "files": previous["files"],
                        "capabilities": previous["required_capabilities"],
                        "reasons": {s["slot"]: s["reason"] for s in previous["selected"]},
                    }
            except (OSError, ValueError, KeyError, TypeError):
                pass
    try:
        decision = prepare_task(
            root,
            event.get("prompt", ""),
            cwd=cwd,
            proposal=proposal,
            allow_acquisition=False,
            seed_only=True,
            session_id=session,
            offline=os.environ.get("CODEX_BOOTSTRAP_OFFLINE") == "1",
        )
    except ValueError:
        if proposal is None:
            raise
        decision = prepare_task(
            root,
            event.get("prompt", ""),
            cwd=cwd,
            seed_only=True,
            session_id=session,
            offline=os.environ.get("CODEX_BOOTSTRAP_OFFLINE") == "1",
        )
    observation = (
        default_cache_dir()
        / "task-hooks-v1"
        / hashlib.sha256(str(root).encode()).hexdigest()
        / (hashlib.sha256(session.encode()).hexdigest() + ".json")
    )
    try:
        atomic_write(
            observation,
            json_text(
                {
                    "hook_event_name": event["hook_event_name"],
                    "decision_id": decision["decision_id"],
                    "selected": [s["key"] for s in decision["selected"]],
                    "prompt_sha256": hashlib.sha256(event.get("prompt", "").encode()).hexdigest(),
                }
            ),
        )
    except OSError:
        pass
    return {
        "hookSpecificOutput": {
            "hookEventName": event["hook_event_name"],
            "additionalContext": task_context(root, decision),
        }
    }


def main():
    try:
        payload = sys.stdin.read(128_001)
        if len(payload) > 128_000:
            raise ValueError("hook input exceeds budget")
        result = handle_event(json.loads(payload))
    except Exception:
        # Never block/discard the user's request or leak its text or subprocess diagnostics.
        result = {
            "systemMessage": "Auto-Skills could not verify task preparation. Continue with general guidance; report the limitation and inspect the local manager before using unverified guides."
        }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
