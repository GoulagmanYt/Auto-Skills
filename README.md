# Auto-Skills

**Explainable Codex guidance for each workspace, maintained as your project changes.**

Auto-Skills reads dependency manifests, selects relevant skills, pins their provenance and refreshes affected workspaces. A Rust backend keeps its own guidance when a React frontend changes. Unknown repositories receive portable guidance with explicit gaps.

**Alpha: 1.4.0a1.** The verified native baseline is Codex CLI **0.166.0**. [Français](README.fr.md) · [Usage](docs/usage.md) · [Coverage](docs/coverage.md) · [Compatibility and evidence](docs/public-alpha.md)

## Install

Requires Python **3.11+**, Git and the original Codex CLI. From a checkout of the intended release:

```powershell
# Windows PowerShell
.\install.ps1
```

```sh
# Linux / macOS
sh install.sh
```

Open a new terminal, then use Codex normally:

```sh
codex -C ./project "Fix backend/src/lib.rs"
codex -C ./project resume
```

The installer preserves the original executable and records its PATH/profile changes for reversal. Preparation uses eligible local skills, public sources allowed by user-global policy, and bundled fallbacks. **Repomix is deferred until explicitly enabled** in the user-global policy. [Automatic operation and optional tools](docs/automatic-skills.md).

## Inspect decisions

In an interactive Auto-Skills session, **F9** opens the repository dashboard. Tabs **1 Skills**, **2 Plugins** and **3 MCP** show installed files, observed reads and tool-call outcomes. **F9**, **Esc** or **Q** returns to Codex with the draft preserved. Plugins without observed calls remain **unverified**. [Controls and evidence limits](docs/usage.md#keyboard-dashboard).

The development agent identifies requirements and delegates guide comparison to **gpt-6-luna with medium effort**, using the existing Codex CLI authentication. The selector records an explicit choice and reason, reused for an identical request. First launch uses a fast bundled starting context with elapsed-time progress on stderr. [Agent selection workflow](docs/ai-selection.md).

```sh
codex-auto-bootstrap propose --repo ./project --offline
codex-auto-bootstrap context --repo ./project
codex-auto-bootstrap check --repo ./project
```

Reports explain workspace boundaries, versions, provenance, exclusions and uncertainty. Declare custom boundaries in [auto-skills.toml](docs/configuration.md). [Diagnostics and recovery](docs/diagnostics.md).

## Integration policy

Default **strict** mode disables external skills, unlisted plugins and MCP servers for the launched profile. To preserve user integrations, put this in `.codex/integrations.toml`:

```toml
[integrations]
mode = "coexist"
```

Allowlisted integrations can also be retained in strict mode. External configuration files are preserved. The original Codex executable bypasses the wrapper; Desktop/IDE clients are outside automatic CLI integration. [Details](docs/usage.md#integrations).

## Update or remove

Rerun the installer from the intended release to update the wrapper. Manifest changes trigger scoped refresh.

Codex CLI updates remain managed by Codex. The wrapper preserves the native launcher path and follows the current standalone release, including installations recorded by older wrapper versions.

```sh
codex-auto-bootstrap refresh --repo ./project --offline
codex-auto-bootstrap uninstall --repo ./project --dry-run
codex-auto-bootstrap uninstall --repo ./project
codex-auto-bootstrap uninstall
```

Repository and wrapper removal are separate. Unrelated edits are preserved; conflicts are explicit. Open a new terminal after wrapper removal. [Reversal](docs/diagnostics.md).

## Evidence and limits

Tests cover workspace isolation, integrity, refresh and uninstall. Installed-package native checks cover the pinned CLI baseline. Historical measurements and failures remain traceable in [the evidence guide](docs/public-alpha.md). Available whole-task samples do not establish token savings or a general performance advantage.

Remote skills are untrusted instructions. Compatibility filters and checksums do not certify safe behavior. [Security model](docs/security-model.md).

## Develop

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
python -m tools.check_docs
```

Unit tests isolate user configuration/cache and block direct network connections. Native checks and inference measurements use explicit, separate commands. [Contributing](CONTRIBUTING.md) · [Architecture](docs/architecture.md) · [Changelog](CHANGELOG.md) · [Release procedure](docs/release.md) · [MIT license](LICENSE)
