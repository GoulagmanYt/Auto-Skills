# Alpha status and evidence

Auto-Skills **1.4.0a1** remains an alpha. Pending maintenance changes are listed under Unreleased in [the changelog](../CHANGELOG.md); they do not create a new release or expand the certified native baseline automatically.

## Supported baseline

Codex CLI **0.166.0**, Python **3.11+**, Windows/Linux/macOS are the initial contract. The archived hosted receipt records 320 tests in each of six OS/Python combinations and installed wheel/sdist native checks on three systems. This evidence applies to its recorded source revision. [Historical hosted receipt](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-hosted-ci.json) and [interpretation with failures and scope](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-followup.md).

The candidate-version workflow is scheduled/manual and separate from pinned release checks. Its presence is not evidence of a completed run or support for another native version. [Compatibility contract](compatibility.md).

## Current verification

Run the isolated unit suite, documentation/publication checks, offline task corpus and installed native verifier documented in [the release procedure](release.md). Current local results belong in `reports/maintenance-validation.json`, with command outcomes, source identity and limitations. Historic records remain in `reports/archive/2026-11-alpha/`; their dates and revisions must not be replaced with current claims.

The expanded synthetic task corpus tests explicit paths, ambiguous current-scope tasks, sibling preservation, unknown/documentary workspaces and multiple target workspaces across Rust, React, Python, Go, Java and C++. The separate pinned public manifests test static extraction and selection, not completed upstream builds or hardware behavior.

## Measurements

Historical whole-task samples do not establish token savings, a general quality advantage or an overall winner. Failures, unavailable usage, interrupted attempts and different source/service states remain visible. [Measurement protocol](benchmark.md) and [historical comparison](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/benchmarks/comparison/analysis.md).

Current startup profiling reports cold/warm preparations and separate phases. A single sample is diagnostic evidence, not a comparative performance claim. Repomix is now deferred by default, so new runs must state their optional-tool policy before comparison with old tool-heavy runs.

## Remaining release boundaries

Native hooks supply task instructions to wrapped CLI launches. Original binaries and arbitrary Desktop/IDE/app-server clients can bypass that integration. Static relevance/version checks remain conservative heuristics. Hardware tasks and native versions beyond the verified baseline need their own evidence.

Forced termination during global installation can require manual snapshot recovery. Repository transactions have journal replay, subject to later-edit conflict checks. Snapshots may contain sensitive configuration. [Diagnostics](diagnostics.md) and [security model](security-model.md).
