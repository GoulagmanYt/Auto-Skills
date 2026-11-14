# Review of automatic skill management

This audit preserves the initial observations. Additional validations and CI actually executed appear in the [follow-up](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-followup.md) and [hosted results](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-hosted-ci.json).

Initial audit: clean tree, commit `85b9bd6`. Work on branch `feat/automatic-task-skills`, without publishing a release or moving a tag. Analysis confirmed the wrapper, manifest/workspace adapters, version filters, GitHub downloads, locking, recoverable transactions and reversible uninstalls. The main gaps were the lack of local inventory before search, per-task decisions and per-request integration; generated instructions still prohibited implicit installations.

The plan followed: local reuse and shared cache; validated decision protocol; launch/resume/request integration; separate deterministic, network and agent evidence; regression review. The code reuses the alpha's mechanisms. No Python runtime dependency, other model service or new API key is required.

## Observed results

Native trial environment: Windows, Python 3.13.17, Codex CLI 0.166.0. Inference trials use existing Codex authentication and the `gpt-6.1-sol` model. Test directories/profiles/registry are isolated; registry access is injected, never applied to the real Windows profile.

| Criterion | Reproducible evidence |
|---|---|
| 1. Automatic first visit | Real installation in a temporary home followed by launching real Codex through its wrapper, without a repository selection command: [demonstration](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills.json) |
| 2. Unchanged return | Zero manager discovery/installation/model analysis calls; lock and file fingerprints/timestamps preserved |
| 3. Eligible local skill | Local Rust guide selected/copied; test forbids any search for a remote equivalent |
| 4. External capability | Vercel guide actually downloaded, commit and SHA-256 recorded, installation and native catalog verified: [network](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-network.json), [agent consultation](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-live.json) |
| 5. Monorepo isolation | Native catalog and backend decision exclude React specialties; mentions of preserving a sibling no longer make it a target |
| 6. Frontend change | Backend resource contents and timestamps preserved; native assertions and existing demonstration retained |
| 7. New task | Same Codex thread resumed to fix the frontend after Rust: new hook observed, selection replaced, JavaScript guide consulted, Node validation and unchanged backend |
| 8. Unknown repository | Useful baseline, explicit uncertainties, zero additional model calls; no invented framework classification |
| 9. Invalid network/source | Existing rejection and outage tests, shared cache usable offline, incompatible license/source/version excluded with local/bundled fallback |
| 10. Interruption/concurrency | Two genuinely concurrent first preparations; process interrupted with `os._exit(73)` after a write, journal present then replayed and lock verified; stress test of 64 cache publications with six threads |
| 11. Uninstallation | Pre-existing instructions restored byte for byte; profile and PATH additions reversed in the test home; pre-existing skills, including a role collision, preserved |
| 12. Real Codex | Catalog actually inspected; guide read commands and consultation markers observed; Cargo/Node independently validate the requested behaviors |

The observed external guide comes from `vercel-labs/agent-skills`, commit `1a2c79d4e6c4a2283dc2c614b6538cbe1ed5ca62`, declared MIT license, instruction SHA-256 `71ed7794962fa6e803ee83030517b5b93a9f70fbfeb431ec4535c5480a8d8355`. The fingerprint identifies this pinned content; it does not certify its semantic safety. Remote consultation is an observation separate from catalog presence.

The successful agent trial fixes truncated Rust headers/frames without panicking, preserves valid/empty frames and trailing bytes, then fixes frontend `null`/`undefined` handling and trimming in the same resumed session. Harness-provided Cargo tests remain unchanged; Node assertions run independently of the agent's final message.

The three observed turns reported 103,280, 207,181 and 104,345 input tokens respectively, a large share of which were cached; details remain in the JSON. These are complete synthetic tasks and a guide consultation, without a comparison arm. They demonstrate neither token savings nor overall superiority. Activated guide counts and preparation latency are recorded separately from inference. The backend task selects nine guides and zero frontend specialties. Missing or unnecessary coverage beyond these fixtures has not been measured on a representative user corpus.

The first ordinary network preparation, without preloading a role or the cache, took **272.76 seconds**, including historical optional tools. It selected/installed the external guide despite 18 reported discovery diagnostics and 149 skill requests. This cold start remains costly; skill discovery bounds do not include downloading/npm installation of existing tools. Offline preparation and return to the same resources are verified separately. The full local suite ran **307 tests, including 5 skips, with no failures**; skipped tests do not constitute validations.

## Preserved failures and fixes

[Attempt 1](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-attempt-1.json): the agent completed Rust, but independent validation failed and Windows sandbox output ACLs prevented cleanup. The initial quota also prevented the full React bundle download.

[Attempt 2](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-attempt-2.json): Rust fix/consultation and independent validation succeeded; remote acquisition still rejected by the quota. [Intermediate network attempt](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-network-attempt-1.json): download possible after fixing the `gh` transport, but the `SKILL.md` license declaration was not recognized. These results remain incomplete/failed in their files.

[Attempt 3](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-attempt-3.json): Rust and frontend tasks correct and remote download successful, but frontend selection retained Rust because of the phrase "preserve the backend". The React guide was not consulted for a purely JavaScript change. Selection now prioritizes targeted paths; the harness measures consultation of the JavaScript guide that is actually relevant.

Controlled inference trials now use `danger-full-access` for their public fixture to avoid Windows sandbox compilation ACLs. The product does not change the user's sandbox choice. Raw outputs, including failures, are preserved locally in `reports/private/` and excluded from distributions and public reports.

## Regression review

An independent read-only review confirmed five issues: concurrent cache eviction, omitted fingerprint for root/workspace-relative targets, manifest drift during a capability request, exclusion of pre-existing repository skills for that request and multiplication of the network budget across scopes. These were fixed with targeted regressions. Collisions with existing skill paths and global exclusion of old `.codex/skills` were also reproduced and fixed. User and manager hook merging was checked with the real `hooks/list`: both sources remain present.

New preparations, capability requests and refreshes use the existing lock/journal. Optional caches remain usable concurrently; cache failure no longer makes verified guides unavailable. Worktrees, repository moves, branch changes and target file changes have separation/invalidation tests. External queries remain composed of roles/technologies, never task text or private code.

Remaining concerns: relevance false positives/negatives in real repositories, native protocol changes, upstream version updates, instruction conflicts and resource consumption of historical optional tools. The first download of these tools can be lengthy; its budget is separate from skill discovery. Bundles and task states remain in the user cache after uninstallation. An abrupt stop can leave an abandoned staging directory; recovery rebuilds a consistent lock and uninstallation preserves unowned files.

## Limits and reproduction

The new native Linux/macOS and Python 3.11 behaviors were not executed on this Windows machine. Corresponding CI is configured; its definition does not constitute a successful run. Before announcing these combinations as verified, run the native matrix and archive its results. The original binary and Desktop/IDE/cloud clients that bypass the wrapper do not receive automatic integration. A global configuration forbidding hooks may retain only launch preparation.

The catalog is configured at launch. Hooks can supply paths to guides installed during a session, without assuming they instantly change native configuration. Consultation by path is the observed fallback; a later launch rebuilds the catalog and forwards the request intact. No general hot reload is claimed.

Catalog presence establishes neither consultation nor correct application. Observed tasks and reads satisfy these states in the fixtures; they do not prove agent compliance with every future instruction. The license is a provenance declaration verified in pinned content, not a legal opinion. Version and relevance parsers remain conservative and bounded.

Commands:

```sh
python -m pip install -e .
python -m unittest discover -s tests -q
python -m ruff check src tests tools
python -m ruff format --check src tests tools
python tools/verify_automatic_skills.py
python tools/verify_automatic_skills.py --network --output reports/automatic-skills-network.json
python tools/verify_automatic_skills.py --agent --network --model gpt-6.1-sol --output reports/automatic-skills-live.json
python tools/demo_workspaces.py
python -m build --outdir dist-alpha
python tools/verify_native_install.py --codex PATH_TO_NATIVE_CODEX --expected-codex-version 0.166.0 --artifact dist-alpha/codex_repo_auto_bootstrap-1.4.0a1-py3-none-any.whl --artifact dist-alpha/codex_repo_auto_bootstrap-1.4.0a1.tar.gz
```

Native distribution verification is recorded in the [wheel/sdist results](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-artifacts.json). Skipped or indeterminate results must remain visible; arms without `--agent` or `--network` are not presented as having executed them.
