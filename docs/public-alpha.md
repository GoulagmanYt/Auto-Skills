# Public alpha readiness

Auto-Skills **1.4.0a1** is an alpha for explainable Codex workspace context, scoped updates and reversible installation.

Repository: https://github.com/GoulagmanYt/Auto-Skills . The original Codex executable can bypass the wrapper. Strict/coexist integration modes have different context guarantees.

## Observed evidence

- Hosted CI at `cdaefaa96a04910a595e32adb7289cee0023a25a`: **11/11 required jobs passed** — Python3.11/3.13 unit tests on Windows/Linux/macOS, three actual installed-package Codex jobs, distribution validation and the selection matrix. Native checks were not skipped. [CI receipt](../reports/hosted-ci.json), [workflow run](https://github.com/GoulagmanYt/Auto-Skills/actions/runs/42070212071).
- Final local verification ran **269 tests:264 passed,5 skipped** for unavailable Windows symlink privileges. Independent actual junction and Git worktree regressions passed. The hosted receipt above remains scoped to its recorded revision; later changes have their own workflow runs.
- Real-manifest coverage: **14/14 pinned public extracts**, with manifest/license SHA-256 values, attribution, static selection and scope-isolation checks. These are manifest extracts, not entire upstream builds. [Matrix](../reports/real-repositories.md).
- Synthetic coverage:18 repositories and15 adversarial checks, zero regressions. [Matrix](../reports/selection-matrix.md).
- Native Codex0.166.0: root/frontend/backend catalogs15/15/14, no duplicated paths, React/Vite excluded from Rust,18 Rust/resource/tool files unchanged across a React update. Temporary user installation/update/uninstall uses injected OS adapters. [Local candidate artifacts](../reports/native-install.json), [public demo](../reports/workspace-demo.json).
- Source publication checks, Ruff lint/format, artifact allowlist/credential/path checks and Twine passed. Local artifact hashes identify local candidate builds; GitHub release artifacts have their own workflow checks and SHA256SUMS.
- Independent reviews identified and rechecked fixes for junction traversal, Julia caret/union semantics, computed CMake standards, installer rollback, selected profiles and platform path aliases.

## Supported and unknown repositories

The adapter registry recognizes the documented static subset of C/C++ CMake/Meson/Conan text, Dart/Flutter, Swift, Elixir, R/renv, Julia and existing ecosystems. Computed executable declarations are not evaluated or numerically certified.

Application, documentation and unknown repositories are distinguished. Unknown input gets portable guidance and local tools with explicit capability/inspection gaps. `auto-skills.toml` adds validated user declarations and provenance without erasing observed evidence. [Coverage](coverage.md), [configuration](configuration.md).

## Task comparison

Historical preflights failed to change a MIDI fixture despite exit zero. Execution recovered after preserving the configured Windows sandbox backend and isolating inherited child-session context; workspace-write restrictions were retained.

The completed45-slot accounting uses three public tasks, three repetitions and five treatment configurations:17 independently validated passes,9 native execution failures,18 adapter/task exclusions and1 interrupted slot with unknown attempt state. All seven genuinely remaining resumed requests passed; no recorded failure was retried. Unknown usage is never zero-filled. [Analysis and measured stages](../reports/benchmarks/comparison/analysis.md), [all per-run receipts](../reports/benchmarks/comparison/report.json).

This is a small observational comparison, not a general superiority claim. Vercel uses one selected React guide; Autoskills uses its pinned installer/registry; SkillRadar uses an unchanged project-local router bundle rather than native marketplace installation. Loaded router presence does not prove it was invoked. Mutable model aliases, shared service caches, native execution errors and source revisions limit inference. [Protocol](benchmark.md).

Performance medians use validated successes only, separately from failure/all-attempt timing. In these small tasks Auto-Skills adds overhead over the bare control. No whole-session token savings or causal speed ranking is established. Source batches and final derivation hashes are kept separately. Six ignored scratch directories remain after conservative cleanup; no temporary benchmark profiles remain in the real Codex home.

## Distribution and remaining limits

The version-tag workflow verifies its artifacts and creates a GitHub prerelease with wheel, sdist and SHA256SUMS. It does not publish to PyPI. Tag only after the exact source revision's required checks pass.

Forced termination or power loss can require manual installer recovery from saved snapshots. Legacy installations without ownership snapshots require manual review. Snapshots can contain sensitive preexisting configuration and must stay private.

Real MIDI/GPIO/LED hardware and Codex versions beyond the pinned0.166.0 baseline are not certified. Static compatibility, license metadata and heuristics are not a semantic security guarantee. No whole-session token or monetary savings are promised from historical startup estimates.
