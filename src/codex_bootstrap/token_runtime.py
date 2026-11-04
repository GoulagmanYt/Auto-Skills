#!/usr/bin/env python3
"""Standalone token-run, copied into the target repository; no package import needed."""

import os
import re
import subprocess
import sys
import tempfile
from collections import deque
from pathlib import Path

SUPPORTED = {
    "git",
    "cargo",
    "npm",
    "pnpm",
    "pytest",
    "ruff",
    "go",
    "dotnet",
    "vitest",
    "jest",
    "playwright",
    "tsc",
    "docker",
}
SIGNAL = re.compile(r"error|fail|warn|exception|traceback|panic|fatal|passed|summary", re.I)


def main():
    args = sys.argv[1:]
    if args[:1] == ["--"]:
        args = args[1:]
    if not args:
        print("usage: token-run -- PROGRAM [ARGS...]", file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parents[2]
    logs = root / ".codex/logs"
    logs.mkdir(parents=True, exist_ok=True)
    fd, log_name = tempfile.mkstemp(prefix="command-", suffix=".log", dir=logs)
    rtk = root / ".codex/bin" / ("rtk.exe" if os.name == "nt" else "rtk")
    name = Path(args[0]).stem.lower()
    # RTK is used only for known transparent commands; arbitrary commands are never replayed.
    if (
        rtk.is_file()
        and name in SUPPORTED
        and Path(args[0]).name == args[0]
        and not os.environ.get("CODEX_TOKEN_RUN_RAW")
    ):
        args = [str(rtk), name, *args[1:]]
    elif os.name == "nt" and not Path(args[0]).suffix:
        import shutil

        args[0] = shutil.which(args[0]) or args[0]
    head, tail, signals = [], deque(maxlen=45), deque(maxlen=30)
    total, previous, repeats = 0, None, 0
    try:
        with os.fdopen(fd, "wb") as log:
            child = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=None, shell=False
            )
            try:
                # Bounded reads also handle a single multi-gigabyte line without retaining it.
                while block := child.stdout.readline(8192):
                    log.write(block)
                    line = block.decode("utf-8", errors="replace").rstrip()
                    line = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", line)
                    total += 1
                    if line == previous:
                        repeats += 1
                        continue
                    if repeats:
                        tail.append(f"[previous line repeated {repeats} times]")
                        repeats = 0
                    previous = line
                    short = line[:1800]
                    if len(head) < 15:
                        head.append(short)
                    else:
                        tail.append(short)
                    if SIGNAL.search(line):
                        signals.append(short)
                code = child.wait()
            except KeyboardInterrupt:
                child.terminate()
                child.wait()
                return 130
            finally:
                child.stdout.close()
        lines = head + list(signals) + list(tail)
        seen, budget = set(), 10000
        for line in lines:
            if line in seen:
                continue
            seen.add(line)
            if budget <= 0:
                break
            print(line[:budget])
            budget -= len(line) + 1
        print(f"[exit {code}; {total} output lines; repeated lines compacted]")
        print(f"Full output: {log_name}")
        return code if code >= 0 else 128 - code
    except OSError as exc:
        print(f"token-run: {exc}", file=sys.stderr)
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
