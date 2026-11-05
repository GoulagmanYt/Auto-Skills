# Recovery setup evidence

These are setup checks, not completed-task inference measurements.

- `autoskills.json`: npm `autoskills@0.4.1` with a source-commit registry override and isolated cache/home installed five frontend recommendations in 8.625 seconds.
- `skillradar.json`: the pinned router skill, lookup script and bundled registry were copied without changing bytes; independent lookup used `local-bundled` registry and ranking `2.1`, completing setup in 1.55 seconds. A separate generated control-profile check enabled exactly one project router skill. Native marketplace/plugin installation was not performed.

Recovery diagnosis is preserved separately:

- `../recovery-env-preflight/report.json`: inherited `CODEX_*` variables removed except `CODEX_HOME`, prior harness otherwise unchanged; failed validator, no patch.
- `../recovery-windows-preflight/report.json`: the same context treatment plus explicit restoration of existing `windows.sandbox="elevated"`; external validator passed and only `midi_state.py` changed. Its historical `status: unavailable` came from a later temporary-directory cleanup `PermissionError`. The report was not rewritten to upgrade that historical status.

The two diagnostic scripts used the pre-recovery harness. The second injected the Windows flag at its subprocess boundary; its original `harness_sha256` identifies that file, not the complete in-memory diagnostic variant. This description records the extra variant. Neither diagnostic disabled the `workspace-write` sandbox or enabled approvals.
