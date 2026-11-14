# Usage

For automatic first visits, task changes, source policy and native lifecycle behavior, see [Automatic skills](automatic-skills.md). The commands below are optional inspection and maintenance tools.

Install from a source checkout using install.ps1 on Windows or install.sh on Linux/macOS. The original Codex binary must already be available. The wrapper installs into a user environment and records owned changes for reversal.

```sh
codex-auto-bootstrap propose --repo ./project --offline
codex-auto-bootstrap bootstrap --repo ./project --offline
codex-auto-bootstrap context --repo ./project --workspace backend
codex-auto-bootstrap context --repo ./project --workspace backend --json
codex-auto-bootstrap check --repo ./project
codex-auto-bootstrap refresh --repo ./project --offline
codex -C ./project/backend
```

`propose` performs no project writes. `context` explains an already installed, verified lock without modifying files; it shows active and excluded guides, reasons, provenance, fallback gaps and a catalog estimate. The estimate uses characters divided by four, not a billing tokenizer, and excludes other native instructions/tools. Use native measurements for empirical prompt comparisons.

A manifest change refreshes affected slots. Unchanged pinned guides and tools are reused. `refresh --all` deliberately reselects all slots. A modified managed artifact fails integrity verification; inspect the change before deciding how to restore it.

## Keyboard dashboard

Interactive repository launches automatically host the unchanged Codex terminal in a pseudo terminal. Press **F9** to open or close the Auto-Skills dashboard. **1**, **2**, **3** or **Tab** switches between Skills, Plugins and MCP. **Up/Down** scrolls, **R** reloads native inventories, and **Esc/Q** returns to Codex. Codex keeps running while the panel is open; the panel does not submit a chat turn or change the composer draft.

Keyboard batches preserve their order when closing the panel. Bracketed paste is forwarded unchanged while Codex has focus and ignored while the read-only dashboard is open, so pasted text cannot invoke panel shortcuts or submit commands.

The dashboard shows managed skill files and their integrity, plugin/MCP inventory and repository integration policy. Auto-Skills manages skills and tooling; it does not install the plugins listed by the native Codex inventory. Strict-mode exclusions remain visible as disabled. Native inventory commands do not start MCP servers or invoke plugin tools.

Usage evidence comes from the manager-owned `PostToolUse` hook. A supported literal file read, including through `token-run`, counts as a consultation when its successful result is known or the actual guide content is present in native text output. Arbitrary dynamic shell/Python reads may remain unobserved. Reading a guide does not certify that the model applied its instructions. Plugin/MCP health describes the latest associated observed call, not a continuing availability guarantee. No call, missing hook evidence or an ambiguous result means **unverified**, not healthy. Plugin association is limited to known MCP declarations; other observed server calls remain visible in the MCP tab.

Evidence is limited to the current wrapper launch and the latest 1,000 relevant tool calls. Only repository-relative guide paths, server names, timestamps and outcomes are retained in the user cache; tool arguments, output, credentials and prompts are not stored. The dashboard never changes hook trust for external plugins or servers.

Refreshes reuse unchanged observation records in memory; changed, replaced or deleted records invalidate those entries. **R** forces a fresh read. Skill integrity still hashes the files on refresh. Malformed evidence is ignored, a broken plugin manifest does not hide other plugins, and native inventory processes are cancelled and reaped when the terminal closes. Text is clipped by display cells so wide characters cannot spill across terminal rows.

Run `python tools/benchmark_dashboard.py` for a reproducible comparison of cached and uncached refreshes using 1,000 synthetic events in an isolated temporary cache. `python tools/verify_dashboard.py --repo . --codex /path/to/codex` checks the real native terminal without sending a model prompt; the native CI matrix also runs this check.

For a terminal without F9, inspect a snapshot with:

```sh
codex-auto-bootstrap dashboard --repo ./project
codex-auto-bootstrap dashboard --repo ./project --json
```

Outside a running wrapper session, this command has no current-session usage evidence. Set `CODEX_BOOTSTRAP_DASHBOARD=0` to use the native terminal directly. Piped/noninteractive commands such as `codex exec` bypass the terminal host automatically. Windows uses ConPTY (Windows 10 1809+); Linux/macOS use the system PTY. There is no native Codex tab extension or binary modification.

## Integrations

Strict mode is the default. Configure a repository using an unowned `.codex/integrations.toml`:

```toml
[integrations]
mode = "strict"
keep_mcp = ["my-notes"]
keep_plugins = ["my-plugin@my-registry"]
```

Use `mode = "coexist"` to preserve external skills/plugins/MCP configuration. The wrapper still filters its own locked guides, but external context may add conflicting guidance or cost. The environment variable `CODEX_BOOTSTRAP_INTEGRATION_MODE` overrides the configured mode for a launch. `context --integration-mode coexist` previews that policy; it does not change future launches.

## Updates and reversal

Upgrade the installed Python package or rerun the source installer from the desired release. Installation keeps the original state record across updates.

```sh
codex-auto-bootstrap uninstall --repo ./project --dry-run
codex-auto-bootstrap uninstall --repo ./project
codex-auto-bootstrap uninstall --dry-run
codex-auto-bootstrap uninstall
```

Project uninstall removes owned artifacts and restores pre-installation instruction/configuration content when safe. User uninstall removes owned launchers and PATH/profile additions. Later unrelated user changes are retained. Changed generated artifacts or ambiguous legacy records can require manual resolution; diagnostics identify the conflict without discarding the file.

After user uninstall, open a new shell to discard inherited PATH/function state. Reinstalling is not required to continue using the original Codex executable.

If the Python package was installed with pip into an existing environment, removing the wrapper preserves that environment and package. Remove the package separately with `python -m pip uninstall codex-repo-auto-bootstrap` when wanted. Source installation owns its private virtual environment.

The wrapper preserves your selected model and reasoning effort, including native profiles and explicit CLI overrides. It does not set a development model or force low effort. The independent guide selector uses its own model and effort. Upgrades remove the old low-effort default only from unchanged, owned generated configuration; user configuration is preserved.

Source-install exceptions roll back from a private recovery copy. A forcibly killed process or power loss may require manual recovery from that saved copy; automatic crash replay is not implemented in this alpha. Preserve the recovery directory and inspect its record before retrying or removing anything.
