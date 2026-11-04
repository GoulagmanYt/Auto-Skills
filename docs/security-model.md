# Security model

Auto-Skills reads manifests/configuration to build profiles. Public GitHub requests contain search terms derived from technology names, not project source. Public discovery caches live outside target repositories.

## Trust boundaries

- Project manifests are input data. Paths used for writes must stay within the intended repository and reject symlinks/junctions that redirect writes.
- Upstream skills are untrusted instructions. Static relevance, compatibility and risky-instruction filters reduce some risks; they cannot prove semantic safety.
- A commit pin and SHA-256 lock detect subsequent changes relative to recorded content. They do not establish upstream identity, benign behavior or license permission.
- Remote skill resources are copied and checked; their scripts are not executed as part of skill installation. Installing optional binary tools is a separate, disclosed operation with pinned sources and integrity checks.
- Codex executes tools with its own permissions and approval model. Auto-Skills is not an operating-system sandbox.

Strict mode disables discovered external skills, bundled guides, unlisted plugins and MCP servers for the launched profile. Explicit allowlists retain selected integrations. Coexist mode preserves user integrations and therefore does not promise an isolated overall catalog. Configuration files for those integrations are not rewritten.

Managed project files are checked before refresh. Later edits cause an integrity failure rather than silent replacement. Uninstall treats user instructions separately from generated artifacts so that removable managed sections and unrelated edits can be preserved. Conflicts must be resolved explicitly; force-deleting user data is not a recovery strategy.

Reversal snapshots in `.codex/original-state.json` contain original bytes of preexisting project instructions/configuration. They can therefore contain sensitive information. Keep `.codex` private and ignored; do not attach snapshots to issues. POSIX snapshots are written with restrictive permissions. User installation records likewise contain original profile state and should stay private.

## Public release hygiene

The source export and wheel/sdist are checked for local state, credentials, private reports and personal absolute paths. Public examples are synthetic. Do not upload Codex authentication files, raw inference logs or private audit output with an issue.

Maintain upstream provenance and license information per skill. Do not redistribute a skill whose license is unknown merely because its repository is public. Use reviewed, pinned sources for maintained demonstrations. Live discovery remains an explicit trust decision with recorded limitations.
