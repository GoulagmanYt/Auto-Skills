"""Measure dashboard evidence refresh using synthetic data in an isolated cache."""

import argparse
import json
import os
import statistics
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from codex_bootstrap.observations import observation_directory, read_observations


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", type=int, default=1000)
    parser.add_argument("--samples", type=int, default=10)
    options = parser.parse_args()
    if not 1 <= options.events <= 1000 or not 1 <= options.samples <= 100:
        parser.error("events must be 1..1000 and samples 1..100")
    with (
        tempfile.TemporaryDirectory(prefix="auto-skills-dashboard-bench-") as temporary,
        patch.dict(os.environ, {"CODEX_BOOTSTRAP_CACHE": temporary}),
    ):
        root = Path(temporary)
        folder = observation_directory(root, "benchmark")
        folder.mkdir(parents=True)
        for index in range(options.events):
            (folder / f"{index:064x}.json").write_text(
                json.dumps(
                    {"version": 1, "time": index, "reads": [], "server": "example", "outcome": "ok"}
                ),
                encoding="utf-8",
            )
        cache = {}
        initial = read_observations(root, "benchmark", cache=cache)
        timings = {}
        for label, selected in (("uncached", None), ("cached", cache)):
            samples = []
            for _ in range(options.samples):
                start = time.perf_counter()
                result = read_observations(root, "benchmark", cache=selected)
                samples.append((time.perf_counter() - start) * 1000)
                if result != initial:
                    raise RuntimeError("cached and uncached evidence differ")
            timings[label + "_median_ms"] = round(statistics.median(samples), 3)
        print(json.dumps({"events": options.events, "samples": options.samples, **timings}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
