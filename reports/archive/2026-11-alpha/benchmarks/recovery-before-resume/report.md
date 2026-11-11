# Complete-task benchmark

Mode: **live**. Model: `gpt-6.1-sol`. Repetitions: 3.

All figures come from completed local measurements. Missing usage remains unavailable; no savings or prices are inferred.

| Task | Arm | Passed | Failed | Unavailable | Median seconds [min, max] | Median input / output / cached tokens |
| --- | --- | ---: | ---: | ---: | --- | --- |
| midi-zero-velocity | baseline | 1 | 2 | 0 | 15.914572 [1.695396, 43.552207] | 151964 / 1188 / 129024 |
| midi-zero-velocity | auto-skills | 2 | 0 | 0 | 57.0355605 [56.423904, 57.647217] | 230500.5 / 1512.0 / 204480.0 |
| midi-zero-velocity | vercel-skills | 0 | 0 | 3 | None [None, None] | None / None / None |
| midi-zero-velocity | autoskills | 0 | 0 | 3 | None [None, None] | None / None / None |
| midi-zero-velocity | skillradar | 0 | 0 | 3 | None [None, None] | None / None / None |
| frontend-reset | baseline | 1 | 1 | 0 | 44.070918 [3.655862, 84.485974] | 436704 / 1753 / 397696 |
| frontend-reset | auto-skills | 1 | 1 | 0 | 45.9529705 [4.839887, 87.066054] | 370596 / 2545 / 326016 |
| frontend-reset | vercel-skills | 1 | 1 | 0 | 42.6553 [7.003131, 78.307469] | 369311 / 2106 / 337536 |
| frontend-reset | autoskills | 1 | 1 | 0 | 49.9436185 [10.181507, 89.70573] | 471020 / 2102 / 434304 |
| frontend-reset | skillradar | 1 | 1 | 0 | 48.8322625 [4.590994, 93.073531] | 407297 / 2092 / 376192 |
| rust-decoder-bounds | baseline | 1 | 1 | 0 | 29.954584500000003 [5.218788, 54.690381] | 188974 / 1401 / 165248 |
| rust-decoder-bounds | auto-skills | 1 | 1 | 0 | 34.1633415 [3.713744, 64.612939] | 211398 / 1493 / 169984 |
| rust-decoder-bounds | vercel-skills | 0 | 0 | 2 | None [None, None] | None / None / None |
| rust-decoder-bounds | autoskills | 0 | 0 | 2 | None [None, None] | None / None / None |
| rust-decoder-bounds | skillradar | 0 | 0 | 2 | None [None, None] | None / None / None |

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
