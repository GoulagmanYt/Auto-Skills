# Reproducible measurements

Two measurements answer different questions:

- Native startup inspection measures exposed catalog/instructions before inference. Historical anonymous results are in reports/startup-context.json. They predate the additional Piano coverage and are not current whole-session savings.
- Complete-task benchmarks run the same task and independent validator against multiple conditions. They record native usage, cached input when available, elapsed time, success, failure and timeouts per run.

The benchmark runner, public synthetic tasks and pinned competitor manifest live in tools/benchmark_tasks.py, examples/benchmark and benchmarks/competitors.json. Use `--help` for exact commands. Start with a dry run, then use an explicit model and repetitions. Inference uses the authenticated Codex CLI and consumes normal account usage.

The deterministic lifecycle demonstration is separate: `python tools/demo_workspaces.py --output reports/workspace-demo.json`. It checks React/Rust isolation and byte/mtime preservation without model calls. It does not measure task token savings.

Compare the same fixture revision, Codex version, model, task prompt and limits. Keep tool/plugin policy comparable and report differences. Repeat each condition, report median and spread, and retain per-run outcomes. Distinguish fresh-process runs from server cache states; do not label a run cold or warm without evidence. Missing usage fields are unavailable, not zero. Do not infer monetary cost without applicable prices.

Competitor discovery/install workflows may not implement the same lifecycle. Record setup failures, unsupported tasks and missing native integrations instead of manufacturing a comparable score. A benchmark harness alone is not a completed competitor benchmark.

Raw model output may contain local paths and must stay outside public artifacts. Publish only sanitized structured results. A small synthetic benchmark is preliminary evidence and must not be presented as broad superiority over competing projects.

The original-project startup script defaults to the user's cache `private-measurements` directory, outside the source tree. Its detailed outputs include target paths and must be explicitly anonymized before publication.

## Historical blocked preflight

The native preflight did not modify its MIDI fixture and failed independent validation despite exit zero. Diagnostic responses reported read-only execution with workspace-write requested; the precise cause is unresolved. A repeated task matrix would not be meaningful under this preflight failure. The [blocked plan](../reports/benchmarks/blocked/report.md) contains 45 unattempted rows, explicit unavailable adapters and retained actual preflight usage. It makes no comparative performance claim.

## Measured recovery run

Execution recovered after preserving the configured Windows sandbox backend and isolating child process context, while retaining workspace-write. [The exploratory comparison](../reports/benchmarks/comparison/analysis.md) accounts for45 slots:17 validated passes,9 native failures,18 harness adapter/task exclusions and1 interrupted/unknown slot. These exclusions do not establish missing upstream product capabilities. All original34 run objects are preserved; seven remaining original requests completed without replaying failures.

Median total/inference/setup timing and token metrics use validated successes only. Separate all-attempt/failure timing and reported usage totals remain available. Missing usage is unknown, not zero. Earlier native failure causes are unresolved, and source/startup/derivation receipts differ. The small interrupted dataset does not establish savings or a general winner.
