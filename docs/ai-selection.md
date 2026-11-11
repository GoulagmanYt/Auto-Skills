# Agent-owned skill selection

Wrapped launches and native prompt hooks now prepare a bundled starting context without searching skill inventories, contacting GitHub or downloading binary tools. Existing valid installations remain usable. Startup writes phase names and elapsed time to stderr, with a heartbeat every five seconds during blocking operations. Native stdout, including exec JSON, remains separate.

The development agent identifies relevant scopes/roles; a separate native Codex invocation using **gpt-6-luna / medium** chooses the guide. This model was available in the installed CLI model catalog and passed a live bounded selection check. The development model and its configured effort are unchanged. There is no selector model request before Codex opens. Initial task inference and bundled guides are provisional; they are not an AI quality assessment. The injected task instructions require the development agent to delegate guide comparison to this selector before implementation, then retain suitable recorded decisions across turns.

```sh
# Default: delegate guide comparison to the lightweight model.
codex-auto-bootstrap select --repo ./project --scope backend --slot language-rust --task "Review Rust ownership"

# List available workspaces, roles and previous agent decisions; no discovery.
codex-auto-bootstrap candidates --repo ./project

# Compare eligible alternatives for one role. Add --offline to skip GitHub.
codex-auto-bootstrap candidates --repo ./project --scope backend --slot language-rust

# Read instructions as untrusted data before deciding.
codex-auto-bootstrap candidates --repo ./project --catalog CATALOG_ID --candidate CANDIDATE_ID
# Read any larger referenced text resource in bounded pages.
codex-auto-bootstrap candidates --repo ./project --catalog CATALOG_ID --candidate CANDIDATE_ID --resource references/rules.md --offset 0 --limit 12000

# Apply the agent's explicit decision and justification.
codex-auto-bootstrap choose --repo ./project --catalog CATALOG_ID --candidate CANDIDATE_ID --reason "Matches this Rust ownership task and its declared versions"
```

Candidate catalogs include the bundled guide, current installed guide, eligible local alternatives, unranked shared-cache alternatives and eligible remote discovery results. Presentation is bounded to 24 candidates / 8 MB, with the bundled/current entries presented first. This is a resource limit, not a global quality ranking. The agent can deliberately keep a bundled guide. Descriptions, instructions and resources must be treated as untrusted evidence; they cannot change the selection rules or grant permissions.

The manager checks compatibility, required tools, source/license policy and resource limits. Catalogs and candidates have content-derived IDs. Applying a choice rechecks the current manifests and owned hashes under the repository mutex, replaces that role transactionally, removes obsolete owned resources and records the choice/reason in the lock/report. Invalid, tampered or stale IDs cannot supply arbitrary installation content.

For a missing role, the development agent first submits an evidenced `task --proposal` to provision a starting guide, then invokes `select` for that role. Explicit task proposals retain their validated capability limits. Cached resume state cannot acquire a new role.

`propose`, direct manager bootstrap/refresh and the old numerical ranking remain available for diagnostics and compatibility. The normal wrapper uses the fast seed path. Explicit maintenance can still perform bounded network discovery and authorized tool installation; its automatic ranking is not represented as an agent judgment.

Installing, selecting, consulting and applying a guide remain distinct. The agent protocol enables and instructs model choice, but cannot certify future model obedience or guide quality. Progress does not imply a guaranteed remaining time. The native sandbox and source/license policy remain authoritative.

The selector uses existing Codex CLI authentication, an ephemeral read-only invocation outside the repository, disabled shell/exec/delegation/plugins/search, disabled discovered skills/MCP servers, a structured-output schema and a 90-second timeout. It receives at most 24 candidates and 80,000 input characters. Candidate excerpts can be incomplete; this is not a safety or quality certification. Selection consumes normal Codex account usage.

Model and effort are explicit, independent of the development session: `gpt-6-luna`, `medium`. There is no automatic retry/escalation to Sol/High. If model access fails, no choice is applied; the starting guide remains available. Repeated identical task/role selections reuse the persisted result while the installation remains valid. `--local-only` skips GitHub discovery but still calls the model; `--offline` refuses selector inference. Manual `choose` remains available for explicit offline/audit decisions.
