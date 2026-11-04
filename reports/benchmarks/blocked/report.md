# Complete-task benchmark

Mode: **blocked**. Model: `gpt-6.1-sol`. Repetitions: 3.

Planned matrix only: attempts below were not executed because the operator designated a failed preflight. No comparative performance result is available.

| Task | Arm | Passed | Failed | Unavailable | Median seconds [min, max] | Median input / output / cached tokens |
| --- | --- | ---: | ---: | ---: | --- | --- |
| midi-zero-velocity | baseline | 0 | 0 | 3 | None [None, None] | None / None / None |
| midi-zero-velocity | auto-skills | 0 | 0 | 3 | None [None, None] | None / None / None |
| midi-zero-velocity | vercel-skills | 0 | 0 | 3 | None [None, None] | None / None / None |
| midi-zero-velocity | autoskills | 0 | 0 | 3 | None [None, None] | None / None / None |
| midi-zero-velocity | skillradar | 0 | 0 | 3 | None [None, None] | None / None / None |
| frontend-reset | baseline | 0 | 0 | 3 | None [None, None] | None / None / None |
| frontend-reset | auto-skills | 0 | 0 | 3 | None [None, None] | None / None / None |
| frontend-reset | vercel-skills | 0 | 0 | 3 | None [None, None] | None / None / None |
| frontend-reset | autoskills | 0 | 0 | 3 | None [None, None] | None / None / None |
| frontend-reset | skillradar | 0 | 0 | 3 | None [None, None] | None / None / None |
| rust-decoder-bounds | baseline | 0 | 0 | 3 | None [None, None] | None / None / None |
| rust-decoder-bounds | auto-skills | 0 | 0 | 3 | None [None, None] | None / None / None |
| rust-decoder-bounds | vercel-skills | 0 | 0 | 3 | None [None, None] | None / None / None |
| rust-decoder-bounds | autoskills | 0 | 0 | 3 | None [None, None] | None / None / None |
| rust-decoder-bounds | skillradar | 0 | 0 | 3 | None [None, None] | None / None / None |

The operator supplied a failed preflight. Planned attempts were not executed and have no repeated measurements.
Preflight report SHA256: `15b4ea8d39cd1272a321c5839295a6730611d218583a8c69db9f98018f2bf06b`. Actual preflight usage is retained separately in JSON evidence.

## Measurement limits

- Auto-Skills includes its developer policy and offline wrappers; it is a treatment bundle, not skills alone.
- Offline Auto-Skills does not install RTK/repomix or discover remote winners.
- Vercel uses manually selected React guidance and is applicable only to the frontend task.
- Same authentication/home and service caches are retained; cache hits are observed, never assumed.
- A requested model identifier is recorded exactly; a mutable service alias is not an immutable model snapshot.
- External validators are public and outside the writable worktree, not secret tests or a malicious-code sandbox.
- Three small synthetic fixes cannot establish general quality, cost or latency superiority.
