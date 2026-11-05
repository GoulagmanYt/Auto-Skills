# Repository configuration

Track ordinary project intent in `auto-skills.toml` at the Git repository root.
The file is optional. It contains no credentials, commands, executable hooks, or
Python imports. Automatic manifest detection continues when it is absent.

```toml
schema_version = 1

[repository]
kind = "auto"

[[workspaces]]
path = "backend"
kind = "application"
technologies = { cpp = "20", cmake = ">=3.22" }
slots = ["language-cpp"]

[[workspaces]]
path = "handbook"
kind = "documentation"
```

Both directories must already exist. A configured directory establishes a
workspace boundary even when its ecosystem has no recognized manifest. The
configuration file itself establishes no framework or application evidence.
Use `path = "."` to declare root technologies or additional root slots:

```toml
schema_version = 1

[repository]
kind = "application"

[[workspaces]]
path = "."
technologies = { cpp = "20", cmake = ">=3.22" }
```

## Schema version 1

Only these keys are supported. Unknown keys and invalid values produce an error
before installation writes. A missing `schema_version` means version 1.

| Location | Key | Value |
|---|---|---|
| Root | `schema_version` | Integer `1` |
| Root | `repository` | Optional table containing `kind` |
| Root | `workspaces` | Optional array of workspace tables, maximum 256 |
| `repository` | `kind` | `auto`, `application`, `documentation`, or `unknown` |
| Workspace | `path` | Required existing directory, relative POSIX path, or `.` |
| Workspace | `kind` | Optional value from the same four kinds |
| Workspace | `technologies` | Optional table of technology identifiers and version strings |
| Workspace | `slots` | Optional array of distinct supported role names |

`auto` requests classification from available evidence. `unknown` explicitly
records that the project kind is unknown. `documentation` uses the documentation
baseline under the automatic preset; `application` uses application guidance.
An explicit command-line preset remains an explicit policy choice. Workspace
kinds apply to that workspace; a root documentation declaration does not erase
an application's own scoped technology guidance.

Technology identifiers match `[a-z][a-z0-9_-]{0,63}`. Values are strings of at
most 100 characters containing conservative numeric version syntax, such as
`"20"`, `"^19.0"`, `">=3.11,<4"`, or `"3.12.*"`. Paths, URLs, credentials,
arbitrary labels, and executable expressions are invalid. Each workspace may
declare at most 128 technologies and 128 slots. The entire file is limited to
64 KiB. Unsupported constraints cannot establish version compatibility simply
because they passed the configuration syntax check.

Slots add requested roles to automatically detected roles. They do not remove
roles or bypass compatibility and tool checks. Names must be supported roles,
such as `language-cpp`, `build-cmake`, `framework-react`, `unit-testing`, or
`security`. Technology declarations infer their mapped roles automatically;
the example's `language-cpp` entry is therefore optional. Unknown technology
identifiers remain visible in the report with a warning when no specialized
capability is mapped. Declaring a technology does not install its compiler or
prove that a matching skill or tool is available.

## Precedence and evidence

Manual technology values control intended versions for candidate selection.
Observed manifest declarations and lockfile resolutions stay in
`technology_sources` and `resolved_versions`; they are not rewritten to agree
with the override. Reports identify manual inputs with `kind = "manual"`,
`path = "auto-skills.toml"`, and the workspace scope. Different observed and
manual values produce a visible declaration-conflict warning for review.

A workspace `kind` overrides `[repository].kind` for `path = "."`. Other
workspace entries apply only to their own scope. Manual declarations never
copy dependency versions to sibling workspaces. With no explicit override,
automatic evidence and its compatibility checks retain their usual behavior.

## Safe paths and refresh

Absolute paths, traversal, backslashes, duplicate scopes, nonexistent
directories, symlinks, junctions, and paths crossing a nested Git repository or
submodule boundary are rejected. Generated and vendor directory components
such as `.git`, `.codex`, `.agents`, `node_modules`, `vendor`, `.venv`, `dist`,
`build`, `target`, and `__pycache__` cannot be configured as workspace roots.
The settings file must also be an ordinary file, rather than a symlink.

Proposals read configuration without installing files. Changing, adding, or
removing the root configuration changes the manifest fingerprint. Status then
reports affected scoped slots; refresh reevaluates their relevant manual
inputs and preserves unchanged sibling artifacts and file modification times.
The configuration is user-owned tracked input, outside the generated integrity
manifest, and is never rewritten by bootstrap or refresh.

## Python integration

`codex_bootstrap.repo_config.read_configuration(root)` returns validated data
with `schema_version`, `repository`, and `workspaces` keys, including the same
empty shape when the file is absent. `configuration_for_scope(root, scope)`
returns that scope's explicit values. `configured_scopes(root)` returns the
validated workspace paths. `apply_configuration(root, profiles)` returns deep
copies with manual intent and provenance applied; callers supply the profiles
for every configured scope. None of these functions execute project code.
