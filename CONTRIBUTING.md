# Contributing

Start with a bug report or a small proposal describing the concrete behavior and an acceptance example. Contributions should preserve workspace isolation, provenance and reversibility.

## Development

Python 3.11+, Git and Codex CLI 0.166.0 are the initial development baseline. Runtime dependencies remain standard-library only.

```sh
python -m venv .venv
python -m pip install -e .
python -m unittest discover -s tests -v
python -m tools.check_docs
python tools/verify_task_selection.py
uv run --no-project --with ruff ruff check src tests tools
uv run --no-project --with ruff ruff format --check src tests tools
```

Activate the virtual environment for your shell before running the pip command. `uv` is an optional development tool; Ruff/build/twine can also be installed into the virtual environment.

For behavior changes, add a regression test and confirm it fails before implementing. Use temporary repositories and homes. Never modify a contributor's actual PATH, shell profiles, Codex credentials or native configuration in tests. Network and inference belong in explicit integration jobs, not unit tests.

Run the native and packaging checks documented in [docs/release.md](docs/release.md), using the verifier's `--artifact` arguments after building. Editable imports are intentionally rejected by the installed-package verifier. Record unsupported versions and failures. New capability mappings need positive and negative workspace relevance cases, direct manifest evidence, slot technologies and concrete fallback guidance.

## Pull requests

Test classes inherit `suite_support.IsolatedTestCase`; isolation wraps `run`, so overriding `setUp` cannot bypass it. Unit fixtures use temporary user/config/cache directories and no real admin skill roots, with direct socket connections blocked. Installed compilers may be used for contract validation; their outputs belong in temporary fixtures. Native installed-package verification and inference are separate explicit tools. See [architecture](docs/architecture.md) for module boundaries and [diagnostics](docs/diagnostics.md) for recovery behavior.

Explain the trigger, resulting behavior and validation. Preserve existing user data; do not silently repair changed managed files or weaken integrity checks. Keep remote downloads bounded and pinned. Add third-party license/provenance information when distributing upstream material. Include public synthetic examples instead of private audits.

Use English for code and primary documentation. French documentation is welcome in README.fr.md. Security disclosures follow [SECURITY.md](SECURITY.md).
