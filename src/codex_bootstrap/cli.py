"""Transparent CLI wrapper. Bootstrap options use a reserved subcommand."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .bootstrap import bootstrap, check, git_root
from .codex_paths import launcher_path
from .config import launch_profile
from .proposal import output_report, propose

PASSTHROUGH = {
    "login",
    "logout",
    "completion",
    "update",
    "doctor",
    "help",
    "features",
    "mcp",
    "plugin",
    "app-server",
    "remote-control",
    "app",
    "debug",
}


def requested_cwd(args):
    cwd = Path.cwd()
    for index, arg in enumerate(args):
        if arg == "--":
            break
        if arg in {"-C", "--cd"} and index + 1 < len(args):
            cwd = Path(args[index + 1]).expanduser()
        elif arg.startswith("--cd="):
            cwd = Path(arg.split("=", 1)[1]).expanduser()
        elif arg.startswith("-C") and len(arg) > 2:
            cwd = Path(arg[2:].removeprefix("=")).expanduser()
    return cwd.resolve()


def requested_prompt(args):
    """Best effort only; stdin remains untouched and per-turn hooks see the real prompt."""
    if "--" in args:
        before, after = args[: args.index("--")], args[args.index("--") + 1 :]
        return " ".join(filter(None, [requested_prompt(before), " ".join(after)]))[:64_000]
    values = {
        "-C",
        "--cd",
        "-c",
        "--config",
        "-m",
        "--model",
        "-p",
        "--profile",
        "-s",
        "--sandbox",
        "-o",
        "--output-last-message",
        "--output-schema",
        "--add-dir",
        "--color",
        "--local-provider",
        "--thread-source",
        "--cyber-access-program",
        "-i",
        "--image",
    }
    positionals = []
    skip = False
    for arg in args:
        if skip:
            skip = False
            continue
        if arg in values:
            skip = True
            continue
        if arg.startswith("-") or arg in {"exec", "resume", "fork", "review"}:
            continue
        positionals.append(arg)
    if positionals and len(positionals[0]) == 36:
        import re

        if re.fullmatch(r"[0-9a-fA-F-]{36}", positionals[0]):
            positionals.pop(0)
    return " ".join(positionals)[:64_000]


def real_codex():
    override = os.environ.get("CODEX_BOOTSTRAP_REAL_CODEX")
    if override:
        path = launcher_path(override)
        if not path.is_file():
            raise ValueError("CODEX_BOOTSTRAP_REAL_CODEX is not a file")
        return [str(path)]
    config = Path.home() / ".local/share/codex-auto-bootstrap/installation.json"
    if config.is_file():
        data = json.loads(config.read_text())
        path = launcher_path(data["real_codex"], migrate_release=True)
        if path.is_file():
            return [str(path)]
    candidate = shutil.which("codex")
    if not candidate:
        raise ValueError("Codex CLI not installed")
    resolved = Path(candidate).resolve()
    if "codex-auto-bootstrap" in str(resolved.parent):
        raise ValueError("recursive wrapper: real Codex path not recorded")
    return [str(launcher_path(candidate))]


def run_codex(root, args, *, real_command=None, offline=False, cwd=None):
    from contextlib import ExitStack

    from .progress import Progress

    real_command = real_command or real_codex()
    env = dict(os.environ)
    env["CODEX_BOOTSTRAP_ACTIVE"] = "1"
    try:
        with ExitStack() as stack:
            launch_args = args
            if root is not None:
                from .native_hooks import hook_overrides
                from .task import prepare_launch

                with Progress() as progress:
                    lock, decision = prepare_launch(
                        root,
                        requested_prompt(args),
                        cwd=cwd,
                        offline=offline,
                        seed_only=True,
                        progress=progress,
                    )
                    extra_bins = [
                        str((root / tool["path"]).parent)
                        for tool in lock["tools"]
                        if tool["name"] == "node" and tool["status"] == "installed"
                    ]
                    env["PATH"] = os.pathsep.join(
                        [str(root / ".codex/bin"), *extra_bins, env.get("PATH", "")]
                    )
                    env["CODEX_BOOTSTRAP_LOCK"] = str(root / ".codex/skills-lock.json")
                    env["CODEX_BOOTSTRAP_REAL_CODEX"] = real_command[0]
                    progress.stage("Checking native hooks and configuring the launch profile")
                    hook_args = hook_overrides(real_command, root)
                    launch_args = stack.enter_context(
                        launch_profile(
                            root, lock, args, cwd, decision=decision, hook_args=hook_args
                        )
                    )
                    progress.stage("Starting Codex; the agent will review the skill candidates")
            return subprocess.call([*real_command, *launch_args], env=env)
    except KeyboardInterrupt:
        return 130


def main(argv=None):
    # Help and reports contain Unicode even through Windows legacy pipes.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if args[:1] in (["candidates"], ["choose"], ["select"]):
            from .agent_selection import apply_choice, candidates, inspect_candidate
            from .progress import Progress

            parser = argparse.ArgumentParser(prog="codex-auto-bootstrap " + args[0])
            parser.add_argument("--repo", type=Path, default=Path.cwd())
            parser.add_argument("--scope", default=".")
            parser.add_argument("--slot")
            parser.add_argument("--catalog")
            parser.add_argument("--candidate")
            parser.add_argument("--reason")
            parser.add_argument("--task", default="")
            parser.add_argument("--local-only", action="store_true")
            parser.add_argument("--resource")
            parser.add_argument("--offset", type=int, default=0)
            parser.add_argument("--limit", type=int, default=12000)
            parser.add_argument("--offline", action="store_true")
            options = parser.parse_args(args[1:])
            root = git_root(options.repo)
            if root is None:
                raise ValueError("not a Git repository")
            if args[0] == "select":
                from .selector import auto_select

                if options.offline or os.environ.get("CODEX_BOOTSTRAP_OFFLINE") == "1":
                    raise ValueError(
                        "model selection needs network; use candidates --offline and choose for offline decisions"
                    )
                with Progress() as progress:
                    result = auto_select(
                        root,
                        options.scope,
                        options.slot,
                        options.task,
                        local_only=options.local_only,
                        progress=progress,
                    )
            elif args[0] == "choose":
                result = apply_choice(root, options.catalog, options.candidate, options.reason)
                result = {"status": "installed", "agent_choices": result["agent_choices"]}
            elif options.catalog and options.candidate:
                result = inspect_candidate(
                    root,
                    options.catalog,
                    options.candidate,
                    resource=options.resource,
                    offset=options.offset,
                    limit=options.limit,
                )
            else:
                with Progress() as progress:
                    result = candidates(
                        root,
                        options.scope,
                        options.slot,
                        offline=options.offline or os.environ.get("CODEX_BOOTSTRAP_OFFLINE") == "1",
                        progress=progress,
                    )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args[:1] == ["task"]:
            from .task import prepare_task, task_context

            parser = argparse.ArgumentParser(prog="codex-auto-bootstrap task")
            parser.add_argument("--repo", type=Path, default=Path.cwd())
            parser.add_argument("--prompt", default="")
            parser.add_argument("--proposal", type=Path)
            parser.add_argument("--session", default=os.environ.get("CODEX_THREAD_ID", "agent"))
            parser.add_argument("--offline", action="store_true")
            parser.add_argument("--json", action="store_true")
            options = parser.parse_args(args[1:])
            root = git_root(options.repo)
            if root is None:
                raise ValueError("not a Git repository")
            proposal = None
            if options.proposal:
                if options.proposal.stat().st_size > 24_000:
                    raise ValueError("task proposal exceeds budget")
                proposal = json.loads(options.proposal.read_text(encoding="utf-8"))
            result = prepare_task(
                root,
                options.prompt,
                cwd=options.repo,
                proposal=proposal,
                session_id=options.session,
                seed_only=True,
                offline=options.offline or os.environ.get("CODEX_BOOTSTRAP_OFFLINE") == "1",
            )
            print(
                json.dumps(result, ensure_ascii=False, indent=2)
                if options.json
                else task_context(root, result)
            )
            return 0
        if args[:1] == ["context"]:
            from .context_preview import inspect_context, markdown_context

            parser = argparse.ArgumentParser(prog="codex-auto-bootstrap context")
            parser.add_argument("--repo", type=Path, default=Path.cwd())
            parser.add_argument("--workspace", type=Path)
            parser.add_argument("--json", action="store_true")
            parser.add_argument("--integration-mode", choices=["strict", "coexist"])
            options = parser.parse_args(args[1:])
            root = git_root(options.repo)
            if root is None:
                raise ValueError("not a Git repository")
            if not (root / ".codex/skills-lock.json").is_file():
                raise ValueError("repository is not initialized; run bootstrap first")
            workspace = (root / options.workspace).resolve() if options.workspace else None
            if workspace is not None and not workspace.is_relative_to(root):
                raise ValueError("workspace must be inside the repository")
            report = inspect_context(root, cwd=workspace, integration_mode=options.integration_mode)
            print(
                json.dumps(report, ensure_ascii=False, indent=2)
                if options.json
                else markdown_context(report)
            )
            return 0
        if args[:1] == ["uninstall"]:
            parser = argparse.ArgumentParser(prog="codex-auto-bootstrap uninstall")
            parser.add_argument("--repo", type=Path)
            parser.add_argument("--home", type=Path)
            parser.add_argument("--dry-run", action="store_true")
            options = parser.parse_args(args[1:])
            if options.repo and options.home:
                raise ValueError("choose --repo or --home")
            if options.repo:
                from .repository_uninstall import uninstall_repository

                root = git_root(options.repo)
                if root is None:
                    raise ValueError("not a Git repository")
                result = uninstall_repository(root, dry_run=options.dry_run)
            else:
                from .installer import uninstall

                result = uninstall(home=options.home, dry_run=options.dry_run)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1 if result["conflicts"] else 0
        if args[:1] in (["bootstrap"], ["propose"], ["refresh"], ["check"]):
            action = args[0]
            parser = argparse.ArgumentParser(prog="codex-auto-bootstrap " + action)
            parser.add_argument("--repo", type=Path, default=Path.cwd())
            parser.add_argument("--offline", action="store_true")
            parser.add_argument("--json", action="store_true")
            parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
            parser.add_argument("--output", type=Path)
            parser.add_argument("--cache-dir", type=Path)
            parser.add_argument(
                "--preset", choices=["auto", "documentation", "minimal", "complete"]
            )
            parser.add_argument("--dry-run", action="store_true")
            parser.add_argument("--all", action="store_true", help="reselect all slots on refresh")
            options = parser.parse_args(args[1:])
            root = git_root(options.repo)
            if root is None:
                raise ValueError("not a Git repository")
            if action == "propose" or options.dry_run:
                report = propose(
                    root,
                    offline=options.offline,
                    cache_dir=options.cache_dir,
                    preset=options.preset or "auto",
                )
                output_report(
                    report,
                    output=options.output,
                    format="json" if options.json else options.format,
                    root=root,
                )
                return 0
            if action == "check":
                result = check(root, preset=options.preset)
                print(json.dumps(result, ensure_ascii=False, indent=2))
                return 0 if result["status"] == "current" else 2
            lock = bootstrap(
                root,
                offline=options.offline,
                refresh_all=action == "refresh" and options.all,
                cache_dir=options.cache_dir,
                preset=options.preset,
            )
            if options.json:
                print(json.dumps(lock, ensure_ascii=False))
            return 0
        if args[:1] == ["install"]:
            from .installer import install

            parser = argparse.ArgumentParser(prog="codex-auto-bootstrap install")
            parser.add_argument("--home", type=Path)
            parser.add_argument("--real", type=Path)
            options = parser.parse_args(args[1:])
            install(home=options.home, real=options.real)
            return 0
        if args and (args[0] in PASSTHROUGH or args[0] in {"--help", "-h", "--version", "-V"}):
            return subprocess.call([*real_codex(), *args])
        cwd = requested_cwd(args)
        root = git_root(cwd)
        return run_codex(
            root, args, offline=os.environ.get("CODEX_BOOTSTRAP_OFFLINE") == "1", cwd=cwd
        )
    except (OSError, ValueError, RuntimeError, TimeoutError, subprocess.SubprocessError) as exc:
        print(f"codex-auto-bootstrap: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
