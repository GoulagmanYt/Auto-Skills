# Release procedure

The current prerelease is `1.4.0a1`. Keep pyproject.toml and codex_bootstrap.__version__ consistent. Version tags are `v<package-version>`.

```sh
python -m unittest discover -s tests -v
uv run --no-project --with ruff ruff check src tests tools
uv run --no-project --with ruff ruff format --check src tests tools
uv run --no-project --with build python -m build --outdir dist-alpha
uv run --no-project --with twine twine check dist-alpha/*
python tools/check_artifacts.py dist-alpha/*.whl dist-alpha/*.tar.gz
python tools/verify_native_install.py --codex codex --expected-codex-version 0.166.0 --artifact dist-alpha/*.whl --artifact dist-alpha/*.tar.gz
```

Use a clean distribution directory for release builds. `--artifact` installs each artifact in a separate fresh environment and runs the native check against that package. Without `--artifact`, the command intentionally rejects editable/source imports; see the workflow for exact platform commands. Development checks against an editable source tree do not replace packaged checks.

Before first publication, review the Git file set and artifact contents, enable private vulnerability reporting, verify repository links, run hosted CI on all platforms and inspect the resulting logs. The release workflow builds and attaches wheel/sdist for a version tag; it does not publish to PyPI. Treat alpha tags as prereleases.

A local Windows result does not establish Linux/macOS success. Keep [public-alpha.md](public-alpha.md) accurate about which checks actually ran. Include failures and known gaps in release notes. PyPI publication, if added later, should use a separately reviewed trusted-publishing workflow.
