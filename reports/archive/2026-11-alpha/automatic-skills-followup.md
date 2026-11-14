# Automatic validation follow-up

This report supplements the [initial audit](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-review.md). Local native trials use Windows, Python 3.13.17, Codex 0.166.0 and existing authentication. Completed cross-platform CI is recorded in the [hosted results](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-hosted-ci.json).

## Observed results

- [Successful persistent session](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-interactive-retry.json): one native process/thread, four turns from Rust → frontend → acquisition/consultation of an additional local capability → Rust. Four independent validations passed, with no new guide from the neighboring workspace consulted. The added capability remains installed. This test explicitly configures app-server; arbitrary app-server clients remain outside automatic integration, with no promise of native hot reload.
- [Preserved failure](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-interactive.json): credits exhausted, zero completed native turns. Observed hooks/selections do not prove task success. The counter now distinguishes attempts from completed turns.
- [Relevance](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-measurement.md): five pinned public manifest excerpts, five correct scopes, five returns with cache reuse and preserved artifacts, with no network or model calls during preparation. A TypeScript role is missed in Vue Reactivity; two static-analysis guides are additional according to the strict annotations. These are not tasks performed in five complete upstream repositories.
- [Complete tasks](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-measurement-tasks.json): three synthetic tasks, two arms, six successful independent validations, one repetition and alternating order. Auto-Skills reports more input tokens for each of the three tasks. Cached inputs are included in these counts. No token or quality improvement is demonstrated.
- Ordinary cold startup: [before](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-startup-before.json) **224.550 s**, [after](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-startup-after.json) **183.996 s**, the same 7,186 owned files including 6,999 tool files. Observed difference: 40.554 s (18.1%), from one pair of measurements subject to network/machine variation. Optional tools are included; approximately three minutes remains costly.

The optimization removes a second full verification immediately after the transaction's verification and replaces repeated resolution of ordinary ancestors with lstat. Profiles go from two full verifications to one. Fingerprints remain verified; links/junctions and unknown reparse points remain checked. Four tests cover redirections and the verification/resolution budget.

## Checks and risks

The full local suite ran 319 tests under Python 3.13 and 3.11, with no failures and five skips per run. After review, the four interactive verifier tests and five measurement tests pass separately, including the new test preserving an interrupted attempt as indeterminate. CI runs the final suite on all three systems and checks distributions with the real Codex catalog.

Independent review found three harness defects, now fixed: loss of interrupted attempts, RPC timeout exceeding the turn budget, and a hardcoded displayed model. No other issue was found in the confinement optimization or the return of the already verified lock. Remaining risks include imperfect relevance, protocol changes, future agent compliance and optional tool costs. Controlled fixtures do not guarantee all future tasks.

## Reproduction

```sh
python -m unittest discover -s tests -q
python tools/verify_interactive_skills.py --codex PATH_TO_NATIVE_CODEX --model gpt-6.1-sol
python tools/measure_automatic_skills.py
python tools/measure_automatic_skills.py --tasks --codex PATH_TO_NATIVE_CODEX --model gpt-6.1-sol
python tools/measure_startup.py --network
```

Raw outputs/profiles remain in `reports/private/`, outside Git and distributions. The interactive trial stops after a native failure; unattempted turns are distinguished by the plan and counters. Task measurements retain all planned rows, even on failure or missing usage. No release or tag is part of this integration.

## Final hosted CI

[Successful run](https://github.com/GoulagmanYt/Auto-Skills/actions/runs/42268009771) at commit 4cba53ee7e1925b701db3750694cab9193676d60: 320 tests in each of the six Linux/macOS/Windows and Python 3.11/3.13 combinations, native Codex 0.166.0 distribution/catalog checks on three systems, build and offline matrix. Optional CI network discovery is skipped; Windows network/inference trials remain separate.

The first macOS runs exposed a temporary fixture alias, fixed without weakening rejection of linked bundles. Windows runs exposed a Rust validator timeout in the reference test. Its test budget is now bounded at 120 s; measured benchmark budgets remain unchanged. Rejection of the faulty fixture must now produce a fingerprint of the executed validator, preventing a timeout or failed compilation from counting as evidence of semantic rejection. These failures and their reruns remain visible.
