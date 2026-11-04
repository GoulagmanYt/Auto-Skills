# Complete-task benchmarks

This harness measures completed code fixes, including executable validation. It is separate from the startup-context measurement in `tools/verify_context_savings.py`. No benchmark outcome is assumed in advance.

Plan the default three repetitions without making inference requests or downloading competitors:

```sh
python tools/benchmark_tasks.py --dry-run --model MODEL --arms baseline,auto-skills --repetitions 3 --output reports/benchmarks/plan
```

Run the same plan with an explicit model and authenticated local Codex CLI:

```sh
python tools/benchmark_tasks.py --model MODEL --arms baseline,auto-skills --repetitions 3 --timeout 180 --output reports/benchmarks/tasks
```

Use `--task midi-zero-velocity`, `--task frontend-reset`, or `--task rust-decoder-bounds` to restrict a run. Repeat `--task` for several tasks. CLI version `0.166.0` is required by default; a deliberate version change requires `--expected-codex-version VERSION`. Prefer an immutable model snapshot. The requested identifier is recorded exactly; a service alias does not establish an immutable underlying snapshot.

`--work-root .benchmark-work` places temporary task repositories under an explicit directory while preserving the `workspace-write` sandbox. This can help diagnose an outer environment that grants writes only below the current repository. Validators still execute from a separate directory outside each agent worktree. The report records the placement policy without publishing the absolute path.

If a smoke run exposes an infrastructure problem, preserve its failed report and expand the intended plan without paying for identical failed calls:

```sh
python tools/benchmark_tasks.py --model MODEL --arms baseline,auto-skills --repetitions 3 --blocked-preflight reports/benchmarks/smoke/report.json --output reports/benchmarks/blocked
```

This is an explicit operator decision, not an automatic assertion that every arm has the same defect. Mode `blocked` records each planned attempt as unavailable and unattempted, with null elapsed/usage measurements. Actual failed-preflight usage is retained separately and tied to the source report hash. It makes no native subprocess calls. Do not present these rows as three completed repetitions.

Each attempt starts with a fresh temporary Git repository containing identical public fixture bytes and a deterministic initial commit. Baseline and Auto-Skills use the same prompt, model, reasoning effort, sandbox and validation. Arm order rotates by repetition. The agent receives the code and task description. The validators and reference fixes stay outside its writable worktree. Before inference, the independent validator must reject the fixture. After inference, it must accept the patch, and every original fixture file other than the requested source file must remain unchanged. Agents may add local tests. No hardware, package installation or network access is needed for the three fixes or their validators.

The harness writes `report.json` and `report.md` after each attempt. Reports include fixture/validator/prompt hashes, fixture commit, requested model and CLI pins, per-run status and elapsed/setup/inference/validation time, native input/output/cached tokens when reported, and success/failure/unavailable counts. Summaries use medians and min/max across attempts with actual measurements, including failed attempts. Each metric reports its sample count; missing usage stays null. A task can pass while native usage is unavailable. No price, savings percentage or cache hit is fabricated. Raw native transcripts, arbitrary error text, environment variables and authentication files are never saved. Diagnostic categories and exit codes are retained instead.

Codex runs as `exec --json --ephemeral --sandbox workspace-write` with explicit model and approval policy. Both arms ignore user configuration and exec rules, disable memories and project documents, and explicitly disable unrelated skills, bundled skills, plugins and MCP servers. Auto-Skills additionally receives its generated developer policy and offline tools. Its `launch_profile` and the control arm briefly create unique native profile files in the original `CODEX_HOME` and remove them in `finally`; authentication is neither copied nor changed. Native CLI cache/runtime side effects may still occur in that original home. The shared service cache is not reset. This measures an Auto-Skills treatment bundle, including policy and wrappers; it cannot isolate the effect of skill prose alone.

`--timeout` is the budget for one task attempt, including preparation. Individual Git, installation, validator and native calls also have bounded timeouts. A native timeout terminates its process group, with an additional bounded cleanup period. Missing runtimes, a mismatched CLI pin and unsupported competitor adapters produce explicit unavailable results. Any failed, timed out or unavailable attempt makes the CLI exit nonzero; dry-run exits zero when the plan is valid.

Optional competitor arms are defined in [competitors.json](competitors.json):

```sh
python tools/benchmark_tasks.py --model MODEL --arms baseline,auto-skills,vercel-skills,autoskills,skillradar --task frontend-reset --repetitions 3 --output reports/benchmarks/competitors
```

- `vercel-skills` uses exact npm `skills@1.7.6` with a checked-out, verified Git commit of Vercel React guidance. Its project-local installer, npm cache/prefix and downloaded source stay in the temporary attempt directory. The manifest records the npm integrity advertised by the registry; npm performs its normal package integrity checks. This is a manually selected React guide and is applicable only to the frontend task. Network/package availability and transitive installer dependencies can still vary.
- `autoskills` records npm `autoskills@0.4.1` and its package source commit. Its recommendation-registry behavior has no audited, isolated adapter here. Native Codex equivalence is not claimed. Requested attempts remain unavailable.
- `skillradar` records the native Codex plugin's `v0.5.0` commit. Its plugin installation/routing model needs a different integration policy from this plugin-disabled comparison. Requested attempts remain unavailable; documented native Codex support is acknowledged.

The package versions were checked against the primary [skills npm registry](https://registry.npmjs.org/skills/1.7.6) and [autoskills npm registry](https://registry.npmjs.org/autoskills/0.4.1). Native installation behavior is documented by [Vercel skills](https://github.com/vercel-labs/skills/blob/7a5e920bead4b1039a6d6df5d7e1163b7b09423a/docs/commands.md) and [SkillRadar](https://github.com/changchangidea-oss/SkillRadar/tree/6354ef44bfe9a8502f4371674ec1c4f8cac5cc56). Codex's [official non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode) describes JSON completion usage and ephemeral execution; local CLI help determines supported flags for the pinned version.

Three small synthetic tasks and three repetitions are a reproducibility smoke test, not evidence of general superiority. Review task success together with latency, usage availability, failed attempts and all policy confounds before drawing conclusions.

Local preflight evidence on 2026-11-04 used Codex `0.166.0`, requested model `gpt-6.1-sol`, baseline and `workspace-write`. A diagnostic MIDI attempt exited zero but changed no code and failed the independent validator; its final agent message reported read-only filesystem access and a rejected inspection command. It took 15.31 seconds and reported 61,481 input tokens, 46,976 cached input tokens, 286 output tokens and 14 reasoning output tokens. A subsequent attempt with its worktree under the outer repository also changed no code and failed validation: 19.211974 seconds, 88,443 input, 73,728 cached input, 311 output and 21 reasoning output tokens. Neither emitted tool execution events. Moving the worktree alone did not resolve the environment restriction. These are failed infrastructure preflights, not successful task runs or comparative results; repeated inference was stopped rather than treating exit zero as success.
