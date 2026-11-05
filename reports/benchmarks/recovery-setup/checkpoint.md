# Benchmark recovery checkpoint

Objective and acceptance: independently validated complete-task observations for three synthetic fixes, baseline and Auto-Skills across tasks, three competitor configurations on frontend; three planned repetitions; no fabricated metrics, hidden retries, global plugin changes, auth copies or sandbox bypass.

Complete accounting: all 45 planned slots recorded: 17 validated passes, 9 native failures, 18 adapter/task-scope exclusions, 1 interrupted slot with unknown attempt state. There are 26 recorded native attempts; the interrupted slot may also have started. Original 34 row objects were preserved exactly. Seven genuinely remaining original requests passed during explicit resumption. Both owned shell sessions have ended.

Changed: tools/benchmark_tasks.py, tests/test_task_benchmark.py, benchmarks/competitors.json, benchmarks/README.md and public recovery/comparison evidence. The child agent made no commit or push. Root integrated code separately.

Decisions: workspace-write/approval never retained; existing Windows sandbox backend preserved while ignoring other native user config; parent orchestration context removed. Cleanup status does not overwrite independently validated results. Autoskills registry/home/cache are pinned and isolated; SkillRadar stages exactly three unchanged router-bundle files with original layout and offline bundled lookup. Scope exclusions do not establish product capability gaps.

Resilience: --resume validates exact pins, preserves completed failures/successes, journals in-flight slots, never replays an ambiguous interrupted request, and stops further new requests on native failure. JSON/Markdown replacement is now atomic; active resumed batch began before that writer improvement, and its original startup receipt remains recorded.

Final analysis: performance total/inference/setup/token medians use validated successes only; all-attempt/failure timing and every known usage total remain separate. Initial and resumed source hashes differ; final derivation has a separate harness hash. Service/cache/model-alias confounds and unresolved earlier native errors preclude a causal ranking or savings claim.

Verified: 15 benchmark tests and scoped Ruff/check-format pass; full 45-slot count, preserved 34-row prefix, and final derivation/run-receipt hashes checked. Known reported usage across 17 successful runs: 5,771,972 input, 5,181,056 cached input, 31,160 output, 957 reasoning output tokens. Usage for nine failed requests and the unknown slot remains unavailable.

Cleanup: no temporary benchmark profiles remain in real Codex home. Six ignored scratch directories remain: normal cleanup was denied for one exact known diagnostic path; other paths lack exact retained ownership receipts. No wildcard deletion or ACL changes.

Final public evidence: reports/benchmarks/comparison/analysis.md, report.json, report.md and README.md. Historical pre-resume snapshot: reports/benchmarks/recovery-before-resume/report.json. Sanitized cleanup: reports/benchmarks/recovery-setup/cleanup.json. Next: root commit/publication/final CI and user report; no more inference or child edits required.
