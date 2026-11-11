# Automatic skills

After the global installation, use `codex` normally in any Git repository. No project selection command or configuration is required. Python 3.11+ and Codex CLI 0.166.0 are the baseline. The [initial audit](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-review.md), [follow-up](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-followup.md) and [hosted CI evidence](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-hosted-ci.json) distinguish observed agent work from installed/catalog checks.

```sh
# Once, from this checkout; Windows: ./install.ps1
./install.sh

codex -C ./project "Fix the Rust decoder in backend/src/lib.rs"
codex -C ./project resume
```

The wrapper covers interactive CLI, `exec`, `resume` and `exec resume`. Launching the original binary bypasses preparation. Desktop, IDE, hosted clients, `codex app` and direct `codex app-server` are not integrated automatically. Native `SessionStart` and `UserPromptSubmit` hooks supply session/resume and per-prompt context. Their availability and hashes are probed from the installed executable, rather than assumed from its version string.

## Preparation

Existing manifest/workspace adapters, version filters, slot selection, transactions and uninstall ownership remain authoritative. Unknown technologies receive common guidance and explicit uncertainty, without an invented framework classification. The current agent can refine a decision; there is no separate model service or new API key.

Before remote discovery, the manager inventories user, repository, plugin-cache and admin skills. Eligible local bundles are copied into owned, hashed locations; originals remain untouched. Unsafe links, missing references, incompatible versions, unsupported declared tools and oversized bundles are rejected. Explicit coexist/keep integration settings remain available for user-managed integrations.

Only locally uncovered roles are searched. Remote winners enter a shared content-addressed cache, reusable by another repository and offline. Reuse repeats source, license, resource and version checks. Searches contain bounded role/technology terms, never repository code, task text, private paths or repository origins. The current built-in connector is public GitHub; its duck-typed `search`/`snapshot`/`blob` interface remains the extension point. Another service needs an adapter and source policy, not a URL supplied by a remote skill.

At launch, task paths and evidenced languages/frameworks select workspace guidance and useful common roles, with at most 20 selected guides. An ambiguous task retains current-scope guidance and states uncertainty. A Rust task at the React/Rust monorepo root selects Rust; a later frontend task replaces that selection. Provisioned backend resources remain reusable without remaining selected.

The agent can submit a proposal as it learns which files matter:

```sh
codex-auto-bootstrap task --repo ./project --proposal decision.json --json
```

```json
{
  "schema_version": 1,
  "scopes": ["frontend"],
  "files": ["frontend/src/App.tsx"],
  "capabilities": ["framework-react", "e2e-testing"],
  "reasons": {"e2e-testing": "Validate the browser behavior of this change"}
}
```

The manager rejects unknown fields, escaping paths, sibling-workspace files, unsupported technology requests and excessive resources. A justified missing portable role, such as browser testing or security, can be acquired through the existing local/discovery/transaction pipeline. The request is persisted so the next integrity check retains that installation. A proposal cannot invent a framework, widen sources, grant script permissions, enable an MCP server or alter global trust. Technology-specific acquisition requires repository evidence.

## Discovery versus use

| State | Required evidence |
|---|---|
| Installed | Committed repository lock and instruction/resource hashes |
| Visible | Actual native catalog, not the lock alone |
| Selected | Validated scope/role decision and exclusions |
| Consulted | Agent tool/transcript evidence or a controlled consultation instruction |
| Applied correctly | Independent checks of the completed task |

Preparation happens before native discovery. A temporary profile enables only the launch selection and supplies explicit guide paths. Later hooks replace the task's consulted selection; they do not claim to rewrite live native configuration. New or previously disabled skills can be read through verified paths. The next wrapper launch rebuilds native configuration and forwards the prompt unchanged. Stdin remains Codex's input. This fallback needs neither a forced restart nor discarding a submitted prompt.

Codex reports the hashes of the manager's hook definitions through `hooks/list`; the manager trusts only its exact matching session-flag handlers. It never uses the blanket hook-trust bypass or trusts project/plugin hooks. User hook files are untouched. The capability result is cached by executable identity and hook definition. If probing fails, launch selection remains available and a diagnostic directs the agent to the task command. That degraded mode is not proof of per-turn automation.

## Global policy and bounds

Global installation authorizes automatic instruction downloads within the source/license policy; there is no per-project or per-skill approval. Optional user-global policy lives at `$CODEX_HOME/auto-skills.toml`, default `~/.codex/auto-skills.toml`:

```toml
[automatic]
repositories = ["openai/skills", "vercel-labs/agent-skills", "anthropics/skills", "trailofbits/skills"]
# Optional heavyweight npm tool. Omit this line to keep it deferred.
optional_tools = ["repomix"]
```

Repository and remote instructions cannot widen that list. Automatic redistribution accepts MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC and CC0-1.0; missing or other licenses lead to a useful local/bundled fallback. This conservative policy excludes some otherwise useful skills.

All workspaces share a 120-second/180-request discovery client. Workspaces needing specialties are evaluated before a root needing only common roles; up to four missing framework/language/database roles receive targeted searches before generic roles. Multi-role registry quotas are 28 each; a targeted single-role search allows 96 per mandatory registry within the same global limit. A failed GitHub CLI transport falls back to HTTPS for that operation family for the remaining discovery, avoiding two attempts per blob. Limits include 80 resources/2 MB per bundle, 18,000 eligible instruction characters, and 256 bundles/64 MB in the shared cache. Concurrent cache maintenance is best effort and cannot invalidate an otherwise admissible installation. Downloading a script does not execute it or install its dependencies. Remote instructions cannot grant permissions, request secrets or trigger arbitrary installations. Correct model obedience remains an observed property, not an OS sandbox guarantee.

## Persistence and reversal

Repomix is planned for relevant repositories but remains `deferred` until this user-global opt-in is present. An online `refresh` installs a deferred tool after opt-in. Offline returns keep the installation unchanged. Already installed tools retain their ownership and pins; removing the opt-in does not silently delete them. RTK remains available through the existing application tool policy. Repository configuration cannot enable optional binary downloads.

The versioned repository lock retains workspaces, manifest fingerprints, pinned provenance, owned hashes and restoration data; its reports explain selections and exclusions. Per-session decisions and native hook observations live outside the project under the user cache (`CODEX_BOOTSTRAP_CACHE` overrides it). Prompts are hashed, not stored. Task, target-file hashes, manifests, selected guide hashes, branch/revision, Git directory and checkout location invalidate task decisions. Worktrees and moved checkouts cannot silently share a task-cache identity. At most 128 decisions per checkout are retained.

Unchanged visits do no skill search, installation or model analysis. Bounded local manifest/policy/integrity checks still run. Pinned resources remain usable without periodic upstream checks; relevant changes or explicit refresh trigger reevaluation. The repository mutex, journal and atomic commit protect both normal preparation and added capability requests. The global source installer retains its documented hard-kill recovery limitation; ordinary exceptions roll back, while repository publication has automatic journal replay.

`CODEX_BOOTSTRAP_OFFLINE=1` disables discovery. Network failure or invalid candidates use valid local/bundled guides with diagnostics. Integrity failures are explicit and never concealed by rewriting the lock. Project uninstall preserves preexisting skills and restores original instructions/configuration. Global uninstall restores owned profile/PATH changes. Shared bundles and task state remain reusable user data; remove the cache separately when desired.

## Reproduction

```sh
python -m pip install -e .
python -m unittest discover -s tests -q
python tools/verify_automatic_skills.py
python tools/verify_automatic_skills.py --network --output reports/automatic-skills-network.json
python tools/verify_automatic_skills.py --agent --network --model YOUR_EXISTING_MODEL --output reports/automatic-skills-live.json
python tools/verify_interactive_skills.py --codex PATH_TO_NATIVE_CODEX --model YOUR_EXISTING_MODEL
python tools/measure_automatic_skills.py
python tools/measure_automatic_skills.py --tasks --codex PATH_TO_NATIVE_CODEX --model YOUR_EXISTING_MODEL
python tools/measure_startup.py --network
```

The default demonstration installs the actual package into a temporary global home, launches native Codex, and checks first visit, unchanged return, new task, targeted frontend update, concurrent first preparations, forced interruption/recovery and restoration. The optional network arm runs ordinary online first preparation with an empty local inventory/cache, installs a real pinned winner and checks native visibility. The agent arm uses existing Codex authentication in place, a public synthetic Rust task, a frontend task resumed in the same thread, and independent Cargo/Node validation. With both flags it also observes the remote guide being read. It explicitly uses `danger-full-access` for those controlled fixtures to avoid Windows sandbox output-ownership effects; production sandbox choice is unchanged.

The native behavior was checked against the official [hook event and trust documentation](https://developers.openai.com/codex/hooks) and [skill discovery documentation](https://developers.openai.com/codex/skills). Only observed client/version combinations in the report are claimed as verified. Live catalog reconfiguration remains a fallback boundary even though file discovery can change automatically.

Raw transcripts and errors stay in ignored `reports/private/`; public reports preserve failures and indeterminate results without credentials or personal paths. The existing native verifier still covers isolated wheel/sdist installs. Recorded whole-task usage is not a claim of token savings or superiority over another setup.

The sustained-session verifier uses one native app-server process and thread with explicit preparation, hook trust and thread configuration. It exercises backend, frontend, a justified additional local capability and backend again. This is a controlled integration test; direct app-server clients still need their own integration. Failed native turns stop the test and remain failed, with attempted and completed turns counted separately.

The measurement tool keeps five pinned public manifest/license extracts and annotations in `fixtures/measurement/`. It measures scope/role errors and unchanged returns offline; these extracts are not full upstream projects. Its optional inference arm uses three separate synthetic tasks, independent validators and both baseline/Auto-Skills arms, retaining failed or unattempted rows. A single repetition cannot establish token savings. Explicit `--refresh` replaces the public sample pins. The startup profiler uses an empty temporary home/cache and defaults to offline; `--network` permits downloads and `--optional-tools repomix` opts into that heavyweight tool inside its isolated policy. It reports cold/warm timings and preparation phases. Full integrity verification remains mandatory; a native launch reuses its one verified lock, and later hook events verify integrity independently.
