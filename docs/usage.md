# Usage

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

The wrapper defaults to low model reasoning effort. An explicit native CLI override such as `codex -C ./project/backend -c 'model_reasoning_effort="high"'` takes precedence for demanding work; skills cannot change a running model's settings.

Source-install exceptions roll back from a private recovery copy. A forcibly killed process or power loss may require manual recovery from that saved copy; automatic crash replay is not implemented in this alpha. Preserve the recovery directory and inspect its record before retrying or removing anything.
