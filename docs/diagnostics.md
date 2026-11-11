# Diagnostics and recovery

Start with these commands; they inspect state and provenance without inference:

```sh
codex-auto-bootstrap check --repo ./project
codex-auto-bootstrap context --repo ./project
codex-auto-bootstrap task --repo ./project --offline --json
codex-auto-bootstrap uninstall --repo ./project --dry-run
```

`check` exits 0 when current and 2 when uninitialized/stale; invalid managed files fail explicitly. `context` explains scope and exclusions. `task --json` includes selected guides, uncertainty and preparation phase timings. A cache hit still verifies integrity.

| Observation | Meaning and next action |
| --- | --- |
| Uninitialized | Launch through the installed wrapper in the Git repository. |
| Stale | Inspect manifest/policy changes and run `refresh`; unchanged sibling workspaces retain pins. |
| Integrity failure | Preserve and inspect the changed managed file before resolving its ownership conflict. Rewriting the lock would hide evidence. |
| Repomix deferred | Default behavior. Enable `automatic.optional_tools=["repomix"]` in the user-global `auto-skills.toml`, then run an online `refresh`. |
| Offline/unavailable tool | Built-in tools and local guides remain available. Retry online when that tool is needed. |
| Native hooks unavailable | Launch selection remains usable. Inspect with `task` when targets change, or start a new scoped launch. Record the native CLI version. |
| Invalid session cache | The manager recomputes the decision. Cached prompts are hashes; cache records cannot authorize capabilities. |
| Another bootstrap running | Wait for that preparation. Process exit releases file locks; avoid deleting a live journal or mutex. |
| Recovery conflict | A later edit would be overwritten. Preserve affected files and the journal; resolve the conflict explicitly. |

Forced termination during the global installer can require manual recovery from saved snapshots. Repository publication uses automatic journal replay. Snapshots can contain sensitive original configuration; keep `.codex` and installation records private.

For slow preparation, run `python tools/measure_startup.py --output reports/private/startup.json` from a source checkout. It defaults to offline and reports cold/warm elapsed time and individual phases. `--network` permits public discovery and RTK installation. Raw profiles stay in `reports/private/`. Its isolated home intentionally ignores existing user policy; add `--optional-tools repomix` to measure that tool explicitly.

Inspect uninstall with `--dry-run`, then remove repository and global wrapper installations separately. Open a new shell afterwards. User caches remain reusable data. [Usage](usage.md) · [Security model](security-model.md) · [Bug reports](../CONTRIBUTING.md)
