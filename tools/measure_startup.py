"""Measure one isolated cold preparation; network/downloads require --network.

Includes optional historical tools. Raw profiles stay private, public rows
contain only module basenames. Single samples do not establish a speedup.
"""

import argparse
import cProfile
import json
import os
import platform
import pstats
import subprocess
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from codex_bootstrap.bootstrap import bootstrap

try:
    from tools.verify_native_install import isolated_environment
except ModuleNotFoundError:
    from verify_native_install import isolated_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network", action="store_true")
    parser.add_argument(
        "--output", type=Path, default=Path("reports/automatic-skills-startup.json")
    )
    parser.add_argument("--evidence", type=Path, default=Path("reports/private/startup"))
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    profiler = cProfile.Profile()
    with tempfile.TemporaryDirectory(prefix="auto-skills-startup-") as temporary:
        root = Path(temporary) / "repository"
        home = Path(temporary) / "home"
        root.mkdir()
        home.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        (root / "package.json").write_text('{"dependencies":{"react":"^19.2"}}')
        env = isolated_environment(home)
        env["CODEX_BOOTSTRAP_OFFLINE"] = "0" if args.network else "1"
        cache = Path(temporary) / "cache"
        with patch.dict(os.environ, env, clear=True):
            started = time.monotonic()
            lock = profiler.runcall(bootstrap, root, offline=not args.network, cache_dir=cache)
            elapsed = time.monotonic() - started
        # The lock/profile contain temporary paths and remain private.
        (args.evidence / "lock.json").write_text(json.dumps(lock, indent=2), encoding="utf-8")
        profiler.dump_stats(str(args.evidence / "startup.pstats"))
        stats = pstats.Stats(profiler).stats
        rows = [
            {
                "module": Path(filename).name,
                "line": line,
                "function": function,
                "calls": values[1],
                "self_seconds": round(values[2], 3),
                "cumulative_seconds": round(values[3], 3),
            }
            for (filename, line, function), values in stats.items()
            if "codex_bootstrap" in filename
        ]
        report = {
            "mode": "ordinary online cold start" if args.network else "offline cold start",
            "platform": platform.system(),
            "python": platform.python_version(),
            "elapsed_seconds": round(elapsed, 3),
            "files": len(lock["files"]),
            "tools": [
                {key: tool.get(key) for key in ("name", "status", "version")}
                for tool in lock.get("tools", [])
            ],
            "profile": sorted(rows, key=lambda row: row["cumulative_seconds"], reverse=True)[:30],
            "limits": "One run; host/network variance and optional tool installation are included.",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"elapsed_seconds": report["elapsed_seconds"], "report": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
