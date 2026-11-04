# Public synthetic task fixtures

These original, anonymous examples contain intentional bugs for reproducible complete-task measurements. They are not imported from private projects. The benchmark copies only one directory below `fixtures/` into each temporary agent repository.

| Task | Intentional bug | Independent validation |
| --- | --- | --- |
| `midi-zero-velocity` | Zero-velocity `note_on` incorrectly activates a note. | Python standard-library checks preserve channel/note identity and note-off behavior without MIDI devices. |
| `frontend-reset` | Reset clears selected IDs but leaves the selection anchor and pending request. | Node assertions check immutable transitions in a JS frontend with an untouched Rust sibling. |
| `rust-decoder-bounds` | A framed decoder indexes missing headers or truncated payloads and panics. | Dependency-free `rustc --test` checks malformed inputs, borrowing, zero length and trailing data. |

Task descriptions are in `tasks.json`. Validators and known reference fixes are separate from fixture repositories and stay outside the agent's writable worktree. Tests execute every validator against both the intentionally broken fixture and the reference fix. Public reference fixes are excluded from the agent prompt and copied worktree; these are public checks, not hidden tests.

See [benchmark usage](../../benchmarks/README.md) for model/CLI pins, measurements, optional competitors and limitations. Do not install the Python/React dependencies just to validate these synthetic fixes; the executable checks use standard libraries only.
