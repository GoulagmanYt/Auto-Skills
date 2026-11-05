# Complete-task benchmark

Mode: **live**. Model: `gpt-6.1-sol`. Repetitions: 3.

Performance medians use independently validated successful attempts only. All failures, interruption and inapplicable slots remain counted separately; missing usage is unavailable. No savings, price or winner is inferred.

| Task | Arm | Passed | Failed | Unavailable | Interrupted | Not attempted | Passed total seconds [min, max] | Passed inference / setup seconds | Passed input / output / cached tokens |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |
| midi-zero-velocity | baseline | 1 | 2 | 0 | 0 | 0 | 43.552207 [43.552207, 43.552207] | 43.202368 / 6e-06 | 151964 / 1188 / 129024 |
| midi-zero-velocity | auto-skills | 2 | 0 | 0 | 1 | 0 | 57.0355605 [56.423904, 57.647217] | 55.9612805 / 0.647486 | 230500.5 / 1512.0 / 204480.0 |
| midi-zero-velocity | vercel-skills | 0 | 0 | 3 | 0 | 0 | None [None, None] | None / None | None / None / None |
| midi-zero-velocity | autoskills | 0 | 0 | 3 | 0 | 0 | None [None, None] | None / None | None / None / None |
| midi-zero-velocity | skillradar | 0 | 0 | 3 | 0 | 0 | None [None, None] | None / None | None / None / None |
| frontend-reset | baseline | 2 | 1 | 0 | 0 | 0 | 87.56392149999999 [84.485974, 90.641869] | 87.20465949999999 / 6e-06 | 402815.0 / 2005.0 / 367552.0 |
| frontend-reset | auto-skills | 2 | 1 | 0 | 0 | 0 | 91.89062999999999 [87.066054, 96.715206] | 89.9763925 / 1.461147 | 438669.0 / 2550.5 / 397120.0 |
| frontend-reset | vercel-skills | 2 | 1 | 0 | 0 | 0 | 90.22478 [78.307469, 102.142091] | 84.0088875 / 4.7821565 | 457861.5 / 2030.5 / 403264.0 |
| frontend-reset | autoskills | 2 | 1 | 0 | 0 | 0 | 92.141012 [89.70573, 94.576294] | 80.168511 / 6.911444 | 457275.0 / 1835.5 / 418880.0 |
| frontend-reset | skillradar | 2 | 1 | 0 | 0 | 0 | 89.32657 [85.579609, 93.073531] | 87.28334699999999 / 1.5735999999999999 | 447797.0 / 2135.0 / 412672.0 |
| rust-decoder-bounds | baseline | 2 | 1 | 0 | 0 | 0 | 57.1733965 [54.690381, 59.656412] | 54.8078405 / 6e-06 | 158885.0 / 1377.0 / 138816.0 |
| rust-decoder-bounds | auto-skills | 2 | 1 | 0 | 0 | 0 | 63.55173 [62.490521, 64.612939] | 60.481333500000005 / 0.637678 | 216201.0 / 1540.5 / 183232.0 |
| rust-decoder-bounds | vercel-skills | 0 | 0 | 3 | 0 | 0 | None [None, None] | None / None | None / None / None |
| rust-decoder-bounds | autoskills | 0 | 0 | 3 | 0 | 0 | None [None, None] | None / None | None / None / None |
| rust-decoder-bounds | skillradar | 0 | 0 | 3 | 0 | 0 | None [None, None] | None / None | None / None / None |

This is an observational interrupted run. All prior failures are preserved; a possibly started unrecorded slot is accounted for separately and is never replayed. Resumed batches have separate harness/source receipts. Native error causes from the original batch remain unresolved when only a generic category was recorded.


## Measurement limits

- Auto-Skills includes its developer policy and offline wrappers; it is a treatment bundle, not skills alone.
- Offline Auto-Skills does not install RTK/repomix or discover remote winners.
- Vercel uses manually selected React guidance and is applicable only to the frontend task.
- Autoskills detects the frontend workspace and installs its own pinned-registry recommendations; this adapter covers only that fixture.
- SkillRadar uses an unmodified project-local router bundle with an offline pinned registry; it is not a native marketplace install and may not activate on these coding prompts.
- Same authentication/home and service caches are retained; cache hits are observed, never assumed.
- A requested model identifier is recorded exactly; a mutable service alias is not an immutable model snapshot.
- External validators are public and outside the writable worktree, not secret tests or a malicious-code sandbox.
- Three small synthetic fixes cannot establish general quality, cost or latency superiority.
