# Public alpha readiness

The release is prepared as **1.3.0a1**. Workflow definitions do not count as successful hosted runs.

The product focuses on Codex workspace isolation, inspectable selection, targeted refresh and reversible installation. The original Codex executable can bypass the wrapper. Strict and coexist integration modes have different context guarantees.

Initial scope includes Python MIDI/LED/GPIO/Raspberry Pi guidance backed by manifest relevance checks. Hardware behavior itself is not certified by hardware-free tests. Third-party skill compatibility is only checked where constraints/evidence are available.

## Observed local evidence

- Windows, Python 3.13.17, actual Codex CLI 0.166.0.
- Final full suite: **206 tests, 202 passed and 4 skipped**, no failures (73.972 seconds). The four skips require symlink privileges unavailable on this Windows host.
- Offline matrix: 18 synthetic repositories, 15 adversarial checks, zero regressions. [Result](../reports/selection-matrix.md).
- Public React/Rust update demo: unchanged backend guide/tool bytes and timestamps. [Result](../reports/workspace-demo.json).
- Wheel/sdist installed independently in fresh environments: native catalogs contain exactly 15/15/14 active guides at root/frontend/backend; no duplicate paths; React/Vite excluded from Rust; 18 Rust/tool files preserved through the React update. Temporary user installation boundaries use injected adapters. [Exact artifacts and evidence](../reports/native-install.json).
- Artifact content/credential/path scans and Twine metadata validation passed. No real user configuration or original Piano/OSC project was modified by integration tests.
- Ruff 0.17.3 lint and format checks passed across all 54 Python files. The staged public source scan covered 115 text files with no flagged personal paths, credential values or local state; local documentation links were checked.
- Independent review verified fixes for Linux venv link ownership, failed-install rollback, empty selector arrays and default Codex profiles.

## Complete-task comparison status

Three real preflight attempts ran against the MIDI task, including one beneath the outer workspace. Native Codex exited normally, changed no source and failed independent validation. Diagnostic responses reported inability to write despite workspace-write; this does not independently establish the underlying permission cause.

The [45-row comparison plan](../reports/benchmarks/blocked/report.md) is explicitly blocked and **unattempted**, not 45 completed or failed task runs. Actual failed-preflight usage is retained separately. No successful comparative task-token, cache, time or quality result is available. Re-run the protocol in a working native execution environment before making performance claims. Autoskills/SkillRadar adapters remain unavailable for reasons recorded in the pinned manifest.

## Before external announcement

- Create the intended GitHub repository, push reviewed source and observe hosted Windows/Linux/macOS jobs.
- Enable private vulnerability reporting and set repository description/topics.
- Publish the version tag after hosted checks pass; the tag workflow creates a prerelease with checked wheel/sdist.
- A broad competitive performance claim requires successful repeated task measurements. This alpha can be presented as workspace-context/lifecycle tooling without that claim.

Forced termination/power loss can require manual installer recovery. Legacy installations without snapshots require manual review. Real hardware, hosted CI and unsupported Codex versions have not been validated by this local run.
