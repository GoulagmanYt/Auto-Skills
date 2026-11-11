# Architecture

Auto-Skills maintains a verified repository installation and supplies task-specific guidance through a Codex CLI wrapper. Runtime dependencies are Python's standard library, Git, and the original Codex CLI.

## Preparation and task flow

1. `cli` preserves native arguments. `task.prepare_launch()` returns one verified lock and its task decision together.
2. `bootstrap` holds the repository mutex, recovers interrupted publication, verifies owned hashes and reads bounded manifests. Unchanged installations return without selection or publication.
3. `profile` aggregates declarations, versions, provenance and capabilities. Static adapters in `adapters` and `manifest_parsers` return `Evidence` without executing project code. `workspaces` and `repo_config` retain boundaries and explicit declarations.
4. `proposal` inventories admissible local/cached skills and discovers missing roles. `selection` checks eligibility before ranking. `catalog` reads fallback prose from the distributed `resources/guides.json` resource.
5. `transaction` journals owned writes and atomically publishes the lock. `lifecycle` reuses unchanged pins/tools. `repository_uninstall` restores original state while preserving unrelated edits.
6. Native hooks call `task.prepare_task()` on prompt/resume events. Each later event verifies integrity again. `decision_state` validates optional v1 records; invalid/unknown records cause recalculation, never authorization.

The lock, profile, transaction journal and session decision have different lifetimes. The lock remains schema v1; journals support v1/v2 recovery. Unsupported session schemas are discarded. Durable schema changes require migrations and previous-version fixtures before changing writers.

## Performance boundaries

Preparation reports milliseconds for entry, integrity, profiling, selection, tools, publication/refresh and total. `tools/measure_startup.py` records one cold preparation and one unchanged return in an isolated temporary home. These timings do not bypass integrity or establish a speedup alone.

Repomix requires a user-global opt-in. Existing installed tools retain ownership/pins until explicit removal; an online refresh can install deferred tools after opt-in. Shared skill bundles already use a content-addressed cache. Sharing executable environments needs a separate ownership, permissions, concurrency and uninstall design; mutable shared npm trees would weaken current guarantees.

GitHub cache maintenance indexes owned entries in memory and reconciles independent writers every 32 writes. Each writer enforces its known count/byte budget; concurrent maintenance remains best effort. Ownership is checked again before eviction.

## Repository layout

| Directory | Responsibility |
| --- | --- |
| `src/codex_bootstrap/` | Distributed runtime and bundled guide resource |
| `tests/` | Unit/contract regressions using `suite_support.IsolatedTestCase` |
| `tools/` | Verification, measurement and maintenance commands |
| `examples/` | Examples users can inspect or adapt |
| `fixtures/` | Synthetic tasks and pinned upstream manifest/license extracts |
| `docs/` | Maintained user, contributor and release documentation |
| `reports/` | Indexed evidence with a dated historical archive |

## Verification layers

Unit fixtures receive a temporary home/cache, no inherited Codex orchestration configuration, no real admin skill inventory and no direct socket connections. Installed compilers remain available, including the explicit rustup toolchain location. Child processes inherit the temporary environment; tests must use disposable fixtures and must never launch inference.

Installed-package native verification is separate and rejects source/editable imports. Pinned Windows/Linux/macOS checks gate releases. A scheduled/manual candidate workflow detects protocol drift without changing the supported baseline. Explicit inference tools retain transcripts privately and report validation, failures and unavailable usage separately. [Protocol](benchmark.md).
