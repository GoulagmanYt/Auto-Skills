"""Demonstrate isolated React/Rust context and a targeted offline refresh."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from codex_bootstrap import __version__
from codex_bootstrap.bootstrap import bootstrap
from codex_bootstrap.context_preview import inspect_context


def demonstrate():
    fixture = Path(__file__).resolve().parents[1] / "examples/workspace-demo"
    with tempfile.TemporaryDirectory(prefix="auto-skills-demo-") as temporary:
        root = Path(temporary)
        shutil.copytree(fixture, root, dirs_exist_ok=True)
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        before = bootstrap(root, offline=True)
        backend = [e for e in before["skills"] if e.get("scope") == "backend"]
        backend_paths = {e[key] for e in backend for key in ("path", "discovery_path")}
        tool_paths = {
            p for p in before["files"] if p.startswith((".codex/bin/", ".codex/plugins/"))
        }
        paths = backend_paths | tool_paths
        for name in paths:
            os.utime(root / name, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))
        states = {p: ((root / p).read_bytes(), (root / p).stat().st_mtime_ns) for p in paths}
        context = inspect_context(root, cwd=root / "backend")
        package = root / "package.json"
        data = json.loads(package.read_text())
        data["dependencies"]["react"] = "^19.1.0"
        package.write_text(json.dumps(data))
        bootstrap(root, offline=True)
        report = json.loads((root / ".codex/bootstrap-report.json").read_text())

        def unchanged(names):
            return all(
                states[p] == ((root / p).read_bytes(), (root / p).stat().st_mtime_ns) for p in names
            )

        result = {
            "version": __version__,
            "mode": "offline; no inference; temporary synthetic repository",
            "backend_workspace": context["workspace"],
            "backend_active_slots": [e["slot"] for e in context["active"]],
            "excluded_root_slots": [e["slot"] for e in context["excluded"] if e["scope"] == "."],
            "backend_files_checked": len(backend_paths),
            "tool_files_checked": len(tool_paths),
            "backend_files_unchanged": unchanged(backend_paths),
            "tools_unchanged": unchanged(tool_paths),
            "refreshed_slots": report["changes"]["refreshed_slots"],
            "retained_slots": report["changes"]["retained_slots"],
            "context": context,
        }
        if not result["backend_files_unchanged"] or not result["tools_unchanged"]:
            raise AssertionError("targeted refresh rewrote unaffected artifacts")
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    text = json.dumps(demonstrate(), indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
