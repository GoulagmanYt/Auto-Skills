"""Integration against public services/native Codex; no model calls or real credentials."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from codex_bootstrap.bootstrap import bootstrap, verify_lock
from codex_bootstrap.config import launch_profile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--online", action="store_true")
    parser.add_argument("--native", action="store_true")
    options = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="bootstrap-smoke-") as directory:
        root = Path(directory)
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        (root / "package.json").write_text(
            json.dumps(
                {
                    "dependencies": {"react": "^19.0.0"},
                    "devDependencies": {"typescript": "^5.7.0", "vitest": "^3.0.0"},
                }
            )
        )
        lock = bootstrap(root, offline=not options.online)
        verify_lock(root)
        print(
            json.dumps(
                {
                    "skills": len(lock["skills"]),
                    "remote": sum(s["source"] == "github" for s in lock["skills"]),
                    "degraded": lock["degraded"],
                    "tools": [
                        {k: t.get(k) for k in ("name", "status", "reason")} for t in lock["tools"]
                    ],
                }
            ),
            flush=True,
        )
        if options.online:
            report = json.loads((root / ".codex/bootstrap-report.json").read_text())
            print(
                json.dumps(
                    {
                        "queries": len(report["discovery"]["queries"]),
                        "remote_candidates": report["discovery"]["remote_candidates"],
                        "search_errors": report["discovery"]["errors"],
                        "rejection_sample": report["discovery"]["rejected"][:8],
                    }
                ),
                flush=True,
            )
            for tool in lock["tools"]:
                if tool["name"] in {"repomix", "rtk"} and tool["status"] != "installed":
                    raise RuntimeError(
                        f"online integration did not install {tool['name']}: {tool.get('reason')}"
                    )
        if options.native:
            codex = shutil.which("codex")
            old = os.environ.get("CODEX_HOME")
            try:
                home = root / "native-home"
                marker = home / "skills/forbidden-global-marker/SKILL.md"
                marker.parent.mkdir(parents=True)
                marker.write_text(
                    "---\nname: forbidden-global-marker\ndescription: FORBIDDEN_GLOBAL_CATALOG_MARKER\n---\nNever load this fixture.\n"
                )
                os.environ["CODEX_HOME"] = str(home)
                with launch_profile(
                    root, lock, ["-C", str(root), "debug", "prompt-input", "test"]
                ) as args:
                    process = subprocess.run(
                        [codex, *args],
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        timeout=45,
                        env=dict(os.environ),
                    )
                    if process.returncode:
                        raise RuntimeError(f"native config failed: {process.stderr[:2000]}")
                    rendered = json.dumps(json.loads(process.stdout))
                    assert "FORBIDDEN_GLOBAL_CATALOG_MARKER" not in rendered
                    assert "Repository skill policy" in rendered
                    for entry in lock["skills"]:
                        assert entry["name"] in rendered, entry["name"]
                    print(
                        json.dumps(
                            {
                                "native": "passed",
                                "locked_skills_visible": len(lock["skills"]),
                                "external_marker": "disabled",
                            }
                        )
                    )
            finally:
                if old is None:
                    os.environ.pop("CODEX_HOME", None)
                else:
                    os.environ["CODEX_HOME"] = old


if __name__ == "__main__":
    main()
