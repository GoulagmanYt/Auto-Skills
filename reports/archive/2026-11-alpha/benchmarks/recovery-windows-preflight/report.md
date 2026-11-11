# Complete-task benchmark

Mode: **live**. Model: `gpt-6.1-sol`. Repetitions: 1.

All figures come from completed local measurements. Missing usage remains unavailable; no savings or prices are inferred.

| Task | Arm | Passed | Failed | Unavailable | Median seconds [min, max] | Median input / output / cached tokens |
| --- | --- | ---: | ---: | ---: | --- | --- |
| midi-zero-velocity | baseline | 0 | 0 | 1 | 55.247483 [55.247483, 55.247483] | 195393 / 1412 / 171648 |

## Measurement limits

- Auto-Skills includes its developer policy and offline wrappers; it is a treatment bundle, not skills alone.
- Offline Auto-Skills does not install RTK/repomix or discover remote winners.
- Vercel uses manually selected React guidance and is applicable only to the frontend task.
- Same authentication/home and service caches are retained; cache hits are observed, never assumed.
- A requested model identifier is recorded exactly; a mutable service alias is not an immutable model snapshot.
- External validators are public and outside the writable worktree, not secret tests or a malicious-code sandbox.
- Three small synthetic fixes cannot establish general quality, cost or latency superiority.
