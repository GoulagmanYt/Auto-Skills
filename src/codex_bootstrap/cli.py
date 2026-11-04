"""Transparent CLI wrapper. Bootstrap options use a reserved subcommand."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .bootstrap import bootstrap, check, git_root
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


def real_codex():
    override = os.environ.get("CODEX_BOOTSTRAP_REAL_CODEX")
    if override:
        path = Path(override).expanduser().resolve()
        if not path.is_file():
            raise ValueError("CODEX_BOOTSTRAP_REAL_CODEX is not a file")
        return [str(path)]
    config = Path.home() / ".local/share/codex-auto-bootstrap/installation.json"
    if config.is_file():
        data = json.loads(config.read_text())
        if Path(data["real_codex"]).is_file():
            return [data["real_codex"]]
    candidate = shutil.which("codex")
    if not candidate:
        raise ValueError("Codex CLI not installed")
    resolved = Path(candidate).resolve()
    if "codex-auto-bootstrap" in str(resolved.parent):
        raise ValueError("recursive wrapper: real Codex path not recorded")
    return [str(resolved)]


def run_codex(root, args, *, real_command=None, offline=False, cwd=None):
    real_command = real_command or real_codex()
    env = dict(os.environ)
    if root is not None:
        lock = bootstrap(root, offline=offline)
        bin_dir = str(root / ".codex/bin")
        # Codex shell subprocesses inherit this, including bundled Node where necessary.
        extra_bins = []
        for tool in lock["tools"]:
            if tool["name"] == "node" and tool["status"] == "installed":
                extra_bins.append(str((root / tool["path"]).parent))
        env["PATH"] = os.pathsep.join([bin_dir, *extra_bins, env.get("PATH", "")])
        env["CODEX_BOOTSTRAP_LOCK"] = str(root / ".codex/skills-lock.json")
        # Prevent model tools from resolving the global codex shim recursively.
        env["CODEX_BOOTSTRAP_REAL_CODEX"] = real_command[0]
    env["CODEX_BOOTSTRAP_ACTIVE"] = "1"
    try:
        if root is None:
            return subprocess.call([*real_command, *args], env=env)
        with launch_profile(root, lock, args, cwd) as launch_args:
            return subprocess.call([*real_command, *launch_args], env=env)
    except KeyboardInterrupt:
        return 130


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
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
