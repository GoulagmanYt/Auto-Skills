# Automatic skills measurement

Relevance uses pinned manifest/license extracts reconstructed as sibling workspaces, not complete public repositories or completed upstream tasks. Complete-task inference uses the separate three synthetic fixtures and independent validators. No token, cost, latency or quality superiority is inferred from either small convenience sample.

## Pinned public manifest relevance

The five language annotations and permitted specialties are stored with the snapshots. Scope and role results include every planned project; missing extracts remain unavailable. Preparation runs offline with isolated inventory. Zero downloads here says nothing about cold network preparation or remote bundle reuse.

| Project | Scope | Missing capabilities | Irrelevant specialties | First / return seconds | Return cache |
| --- | --- | --- | --- | --- | --- |
| [psf/requests](https://github.com/psf/requests/blob/3c7baaa05ab4aa49cc819ce3a819d260de19c157/pyproject.toml) | requests | none | static-analysis | 2.421602 / 1.835818 | True |
| [sharkdp/bat](https://github.com/sharkdp/bat/blob/408801f2a768a75f2db5b3608d9d2edac8406b20/Cargo.toml) | bat | none | none | 1.857713 / 1.852439 | True |
| [cli/cli](https://github.com/cli/cli/blob/eeb44bc432c0107de002dadd34a61b4e2bd15882/go.mod) | github-cli | none | none | 1.895659 / 1.877977 | True |
| [expressjs/express](https://github.com/expressjs/express/blob/43fca52d28a422c8be48fd489cbd4f2d6152bab6/package.json) | express | none | static-analysis | 1.846668 / 1.853997 | True |
| [vuejs/core](https://github.com/vuejs/core/blob/8b479a89445868d474f17e2d837765e7c9ece5e4/packages/reactivity/package.json) | vue-reactivity/packages/reactivity | language-typescript | none | 1.842289 / 1.844053 | True |

## Complete synthetic tasks

One repetition, alternating arm order by task; gpt-6.1-sol with existing Codex auth, low reasoning, equal danger-full-access in disposable public fixtures. The wrapper reuses the existing fixture setup, contract checks and independent validators, replacing preparation with offline task-scoped selection. No remote guides or hooks are evaluated. Native logs are private; hashes and native usage are public. Shared authentication/service caches are retained. Every planned row, failure and missing usage is shown.

| Task | Arm | Status | Validator | Seconds | Input | Cached input | Output |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| midi-zero-velocity | baseline | passed | passed | 44.239586 | 154129 | 137856 | 1343 |
| midi-zero-velocity | auto-skills | passed | passed | 49.68849 | 230948 | 204160 | 1497 |
| frontend-reset | auto-skills | passed | passed | 60.418803 | 240526 | 218624 | 1659 |
| frontend-reset | baseline | passed | passed | 50.44409 | 190362 | 167424 | 1255 |
| rust-decoder-bounds | baseline | passed | passed | 44.731477 | 159198 | 136704 | 1284 |
| rust-decoder-bounds | auto-skills | passed | passed | 57.510988 | 170591 | 150016 | 1289 |

Input tokens include cached input; the columns must not be added together. Missing reasoning-token fields remain null. Totals in JSON include all reported attempts, including failures. This small single-repetition sample does not support savings claims or a general winner.

Reproduce: `python tools/measure_automatic_skills.py`; refresh public pins explicitly with `--refresh`; run inference explicitly with `--tasks --model gpt-6.1-sol --codex PATH_TO_NATIVE_CODEX`. The pinned extracts and provenance are in `examples/measurement/`. Refreshing selects new commits and therefore changes the sample.
