# Benchmark recovery checkpoint

Objective: real independently validated complete-task comparison, three repetitions of baseline/Auto-Skills on three public fixtures plus Vercel, autoskills and the SkillRadar router bundle on the frontend fixture. Acceptance: 27 bounded native requests, exact pins and usage, all failures retained; no comparative claim inferred from setup or blocked plans.

Changed: `tools/benchmark_tasks.py`, `tests/test_task_benchmark.py`, `benchmarks/competitors.json`, `benchmarks/README.md`, new recovery report directories. No commits or pushes.

Decisions: retain workspace-write/approval never; preserve existing Windows sandbox backend while ignoring other native user config; remove parent orchestration context; report cleanup separately. Autoskills registry pinned and isolated; SkillRadar stages exactly three unmodified router-bundle files, not marketplace integration.

Verified: 11 benchmark tests and scoped Ruff pass. Sanitized-context-only diagnostic failed; adding existing elevated Windows backend produced a validator-accepted baseline patch with historical cleanup status unavailable; final Auto-Skills diagnostic passed with completed cleanup. Real isolated competitor setup checks passed.

Current: full 45-row matrix (27 applicable inference attempts + 18 inapplicable rows) is running sequentially with 120-second per-attempt budgets in `reports/benchmarks/recovery-measured` (owned shell session 7849). First baseline MIDI passed. Startup source receipt differs from current due root-disclosed formatting during launch; preserve initial receipt, add explicit source-change disclosure and separate final hash after completion. No paid reruns for formatting only.

Next: wait on actual running process, interpret complete measured results, and report limitations. Preserve historical `blocked` report. Aggregate actual native usage and success/latency with causal limitations.
