# Evidence index

Historical alpha receipts are under [archive/2026-11-alpha](archive/2026-11-alpha/README.md). JSON receipts retain original bytes, failures, source identities and limitations. Archive Markdown links point to the original source revision.

Current offline evidence: [12 task-selection cases](task-selection.json), [14 pinned upstream extracts](real-repositories.json), and [one cold/warm preparation profile](preparation-offline.json). The startup profile uses the default deferred optional-tool policy and is not comparable to historical online, tool-heavy runs. Each result has a narrower scope than a completed real-world task benchmark.

The [maintenance validation receipt](maintenance-validation.json) records the exact source-content fingerprint, both local Python suites, four installed-artifact native checks, review outcomes and verification limits. [Automatic native lifecycle checks](automatic-skills-maintenance.json) retain the observed concurrency, interruption/recovery and uninstall results separately.

| Question | Evidence |
| --- | --- |
| What passed on hosted platforms? | [Final receipt](archive/2026-11-alpha/automatic-skills-hosted-ci.json) and [interpretation](archive/2026-11-alpha/automatic-skills-followup.md) |
| Do scoped updates preserve sibling artifacts? | [Workspace demonstration](archive/2026-11-alpha/workspace-demo.json) |
| Which upstream extracts were checked? | [Real-repository matrix](archive/2026-11-alpha/real-repositories.md) |
| What does the comparison establish? | [Analysis](archive/2026-11-alpha/benchmarks/comparison/analysis.md) and [canonical receipt](archive/2026-11-alpha/benchmarks/comparison/report.json) |
| What were the relevance/performance limits? | [Measurement](archive/2026-11-alpha/automatic-skills-measurement.md) and [startup profile](archive/2026-11-alpha/automatic-skills-startup-after.json) |

New current receipts belong outside the archive and must state source identity, platform, commands, results/skips and limits. A workflow definition does not establish a completed hosted run. Checkpoints, credentials, raw transcripts and private measurements remain excluded from publication.
