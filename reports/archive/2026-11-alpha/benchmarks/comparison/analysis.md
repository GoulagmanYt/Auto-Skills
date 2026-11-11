# Exploratory complete-task comparison

All 45 planned slots are accounted for: **17 independently validated passes, 9 native execution failures, 18 adapter/task-scope exclusions, and 1 interrupted slot with unknown attempt state**. There were 26 recorded native attempts; the interrupted slot may also have started. It was not replayed. No recorded failure was retried.

This is an interrupted observational comparison, with one or two validated successes per condition. It does not support an overall winner, a causal speed ranking, a token-savings claim or a cost estimate.

| Task | Condition | Validated n | Failed | Interrupted | Total seconds | Inference seconds | Setup seconds |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| midi-zero-velocity | baseline | 1 | 2 | 0 | 43.55 | 43.20 | 0.00 |
| midi-zero-velocity | auto-skills | 2 | 0 | 1 | 57.04 | 55.96 | 0.65 |
| frontend-reset | baseline | 2 | 1 | 0 | 87.56 | 87.20 | 0.00 |
| frontend-reset | auto-skills | 2 | 1 | 0 | 91.89 | 89.98 | 1.46 |
| frontend-reset | vercel-skills | 2 | 1 | 0 | 90.22 | 84.01 | 4.78 |
| frontend-reset | autoskills | 2 | 1 | 0 | 92.14 | 80.17 | 6.91 |
| frontend-reset | skillradar | 2 | 1 | 0 | 89.33 | 87.28 | 1.57 |
| rust-decoder-bounds | baseline | 2 | 1 | 0 | 57.17 | 54.81 | 0.00 |
| rust-decoder-bounds | auto-skills | 2 | 1 | 0 | 63.55 | 60.48 | 0.64 |

Timing medians above use only rows that passed the external validator. Inference includes launch-profile preparation and native execution; total includes fixture preparation, setup, inference, validation and cleanup. Competitor setup includes fresh isolated installers/downloads, while Auto-Skills uses local offline bootstrap. Separate medians need not sum to the total median. The JSON retains all-attempt/failure timing and sample counts.

| Task | Condition | Validated n | Input tokens | Output tokens | Cached input tokens |
| --- | --- | ---: | ---: | ---: | ---: |
| midi-zero-velocity | baseline | 1 | 151,964.0 | 1,188.0 | 129,024.0 |
| midi-zero-velocity | auto-skills | 2 | 230,500.5 | 1,512.0 | 204,480.0 |
| frontend-reset | baseline | 2 | 402,815.0 | 2,005.0 | 367,552.0 |
| frontend-reset | auto-skills | 2 | 438,669.0 | 2,550.5 | 397,120.0 |
| frontend-reset | vercel-skills | 2 | 457,861.5 | 2,030.5 | 403,264.0 |
| frontend-reset | autoskills | 2 | 457,275.0 | 1,835.5 | 418,880.0 |
| frontend-reset | skillradar | 2 | 447,797.0 | 2,135.0 | 412,672.0 |
| rust-decoder-bounds | baseline | 2 | 158,885.0 | 1,377.0 | 138,816.0 |
| rust-decoder-bounds | auto-skills | 2 | 216,201.0 | 1,540.5 | 183,232.0 |

Native usage was reported for the 17 successful attempts: **5,771,972 input tokens, including 5,181,056 cached input tokens; 31,160 output tokens; and 957 reasoning output tokens**. Usage is missing for nine recorded failed attempts and the interrupted slot. These are known reported totals, not complete charges or prices. Recovery diagnostics and isolated installer checks are separate from this matrix.

The 18 excluded combinations reflect the adapters and task scopes configured by this harness. They do not establish that Vercel, autoskills or SkillRadar products lack MIDI or Rust capabilities. Vercel uses a manually selected React guide; autoskills installs its own pinned-registry recommendations; SkillRadar uses three unchanged files from its plugin router bundle with the bundled registry, rather than native marketplace integration. Installed guidance does not prove model activation.

The original runner disappeared after saving 34 rows. Their row objects are unchanged in the final receipt. Eight original failures exited 1 with generic native error/turn-failed events; their raw messages were deliberately discarded, so quota, authentication or provider causes are not established. One attempt exited 1073807364 before tool events. The first ambiguous pending slot was conservatively marked interrupted, and all seven genuinely remaining planned requests subsequently passed.

Requested model: `gpt-6.1-sol` (mutable service alias). Native CLI: `0.166.0`. Product version: `1.4.0a1`. The initial and resumed batches have different source hashes, and the final summary has a separate derivation hash. Original startup receipts are preserved; this is not an immutable clean-commit comparison. Service/cache state was retained and neither source changes nor earlier failure causes can be isolated from this small sample.

No temporary benchmark profiles remained in the real Codex home after completion. Six ignored scratch directories remain: ordinary cleanup was denied for one exactly attributed directory, and the others lacked an exact retained path receipt. No broad deletion, permission change, authentication copy or sandbox bypass was used.

[Full per-run receipts, source hashes, usage and derived metrics](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/benchmarks/comparison/report.json) · [Generated detailed table](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/benchmarks/comparison/report.md) · [Pre-resume historical snapshot](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/benchmarks/recovery-before-resume/report.json)
