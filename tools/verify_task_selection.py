"""Evaluate pre-annotated workspace tasks offline; keep every outcome visible."""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from codex_bootstrap.fs import confined
from codex_bootstrap.task import prepare_task

try:
    from tools.verify_native_install import isolated_environment
except ModuleNotFoundError:
    from verify_native_install import isolated_environment

CORPUS = Path(__file__).resolve().parents[1] / "fixtures/task-selection.json"


def verify_tasks(corpus=CORPUS):
    spec = json.loads(corpus.read_text(encoding="utf-8"))
    if spec.get("schema_version") != 1:
        raise ValueError("unsupported task corpus schema")
    rows = []
    with tempfile.TemporaryDirectory(prefix="auto-skills-task-corpus-") as temporary:
        directory = Path(temporary).resolve()
        root, home = directory / "repo", directory / "home"
        root.mkdir()
        home.mkdir()
        subprocess.run(
            ["git", "init", "-q", str(root)], check=True, capture_output=True, timeout=30
        )
        for relative, text in spec["files"].items():
            path = confined(root, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        environment = isolated_environment(home)
        environment["CODEX_BOOTSTRAP_CACHE"] = str(directory / "cache")
        with (
            patch.dict(os.environ, environment, clear=True),
            patch("codex_bootstrap.config.external_skills", return_value=set()),
            patch(
                "urllib.request.urlopen",
                side_effect=AssertionError("offline corpus attempted network"),
            ),
        ):
            for case in spec["cases"]:
                cwd = confined(root, case.get("cwd", "."))
                first = prepare_task(
                    root, case["prompt"], cwd=cwd, offline=True, session_id=case["id"]
                )
                second = prepare_task(
                    root, case["prompt"], cwd=cwd, offline=True, session_id=case["id"]
                )
                slots = {entry["slot"] for entry in first["selected"]}
                missing = sorted(set(case["required"]) - slots)
                irrelevant = sorted(set(case["forbidden"]) & slots)
                rows.append(
                    {
                        "id": case["id"],
                        "expected_scopes": case["scopes"],
                        "actual_scopes": first["scopes"],
                        "missed_capabilities": missing,
                        "forbidden_selected": irrelevant,
                        "return_cache_hit": second["cache_hit"],
                        "passed": sorted(first["scopes"]) == sorted(case["scopes"])
                        and not missing
                        and not irrelevant
                        and second["cache_hit"],
                        "selected": [
                            {"scope": s["scope"], "slot": s["slot"]} for s in first["selected"]
                        ],
                    }
                )
    passed = sum(row["passed"] for row in rows)
    return {
        "schema_version": 1,
        "evidence_scope": spec["description"],
        "cases": rows,
        "summary": {"planned": len(spec["cases"]), "passed": passed, "failed": len(rows) - passed},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    report = verify_tasks()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"]))
    if report["summary"]["failed"]:
        print(json.dumps([r for r in report["cases"] if not r["passed"]]))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
