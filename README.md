# Auto-Skills

**An explainable Codex skill context for each workspace, maintained as your project changes.**

Auto-Skills profiles dependency manifests, selects a guide per role and workspace, pins the results, and refreshes affected guides when a manifest changes. A React frontend keeps its own guidance while a Rust backend sees its own stack and portable shared guides.

**Status: 1.4.0a1 alpha.** Initial native compatibility is tested with Codex CLI **0.166.0**. [Français](README.fr.md) · [Usage](docs/usage.md) · [Coverage](docs/coverage.md) · [Release evidence](docs/public-alpha.md)

## Try it

Requirements: Python **3.11+**, Git and the original Codex CLI. From this source checkout:

```powershell
# Windows PowerShell
.\install.ps1
```

```sh
# Linux or macOS
sh install.sh
# Open a new shell, or launch immediately using:
"$HOME/.local/share/codex-auto-bootstrap/bin/codex"
```

The installer creates user launchers and records PATH/profile changes for reversal. It preserves the original Codex binary. Inspect and provision an existing Git repository:

```sh
codex-auto-bootstrap propose --repo ./project --offline
codex-auto-bootstrap bootstrap --repo ./project --offline
codex-auto-bootstrap context --repo ./project --workspace backend
codex -C ./project/backend
```

`propose` performs no project writes. `context` explains an installed, verified lock without changing files: active/excluded guides, reasons, provenance, fallback gaps and an estimated catalog cost. The estimate is not a billing measurement.

Offline mode uses bundled guides and local Python tools. Normal online provisioning can discover pinned upstream guides and download the optional tools listed in the proposal. Read the plan before choosing that behavior.

## Any repository, explicit limits

Application, documentation and unknown repositories have distinct plans. Unsupported projects remain usable with portable guidance and no speculative tool downloads. C/C++/CMake/Meson, Flutter/Dart, Swift, Elixir, R and Julia now have static adapters alongside the existing ecosystems. A README never turns unknown application files into documentation evidence.

Declare custom workspace boundaries, intended versions or repository kind in [auto-skills.toml](docs/configuration.md). Manual inputs retain provenance and do not erase observed manifest/lock evidence. [Coverage and parser limits](docs/coverage.md).

## What you can verify

| Behavior | Evidence |
|---|---|
| One active native discovery path per guide | Packaged real-Codex check in `tools/verify_native_install.py` |
| Rust excludes React/Vite root guidance | Workspace integration tests and native catalog assertions |
| React updates preserve Rust skills and tools | Targeted refresh tests and public demonstration |
| Selection explains constraints, provenance and exclusions | `propose` and `context` commands |
| Installation reverses without discarding unrelated edits | Temporary-home/profile/PATH and project uninstall tests |
| Piano guidance follows relevant Python dependencies | Positive and negative MIDI/LED/GPIO/Raspberry Pi relevance tests |

Run the public React/Rust demonstration with `python tools/demo_workspaces.py`. Its [recorded result](reports/workspace-demo.json) shows which guides are excluded and which files remain unchanged. It uses a temporary synthetic repository and no inference.

## Integrations are explicit

Default **strict** mode disables discovered external skills, bundled native guides, unlisted plugins and MCP servers for the launched profile. External configuration files are not rewritten. Keep selected integrations with allowlists or opt into **coexist** in `.codex/integrations.toml`:

```toml
[integrations]
mode = "coexist"
```

Coexist preserves user integrations and filters Auto-Skills' own guides. External context can add cost or conflicting instructions. [Policy and allowlists](docs/usage.md#integrations).

The standalone Codex executable bypasses the wrapper. These policies are not an OS sandbox. Workspace activation happens at launch; start a scoped session with `-C` for the workspace you are changing.

## Update or remove

Rerun the installer from the intended release to update the wrapper. Manifest changes trigger targeted guide refresh at the next launch. `refresh --all` deliberately reselects all guides.

```sh
codex-auto-bootstrap check --repo ./project
codex-auto-bootstrap refresh --repo ./project --offline
codex-auto-bootstrap uninstall --repo ./project --dry-run
codex-auto-bootstrap uninstall --repo ./project
codex-auto-bootstrap uninstall
```

Project and wrapper removal are separate. Later unrelated edits are retained; changed generated artifacts or ambiguous legacy records require explicit conflict resolution. Open a new shell after wrapper removal. [Reversal details](docs/usage.md#updates-and-reversal).

## Measurements and limits

Historical startup estimates showed 16,079 → 13,045 tokens for Piano and 16,079 → 13,366 for OSC. They predate the extra Piano coverage and integration modes in this alpha. They describe one startup environment, not whole-session, billing or cache savings. [Anonymous evidence](reports/startup-context.md).

The [complete-task benchmark](docs/benchmark.md) uses public synthetic fixtures, model/version pins, repetitions and independent validators. Failures and unavailable competitor arms remain visible. A harness or a passing unit suite does not establish superiority.

Remote skills are untrusted instructions. Declared compatibility and relevance use conservative heuristics; undeclared compatibility is not certified. SHA-256 detects changes relative to recorded content, not safe behavior. Upstream licenses remain applicable. [Security model](docs/security-model.md).

## Develop

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
uv run --no-project --with build python -m build --outdir dist-alpha
python tools/verify_native_install.py --codex codex --expected-codex-version 0.166.0 --artifact dist-alpha/*.whl --artifact dist-alpha/*.tar.gz
```

The native check uses temporary repositories/homes and makes no inference request. CI definitions cover Windows/Linux/macOS and packaged artifacts; consult release evidence for completed runs.

[Contributing](CONTRIBUTING.md) · [Security reporting](SECURITY.md) · [Changelog](CHANGELOG.md) · [Release procedure](docs/release.md) · [MIT license](LICENSE)
