# Repository coverage

Auto-Skills accepts Git repositories with supported, partially supported or unknown project types. Acceptance is not a claim to understand every framework or execute every build system.

## Classification

- **Application:** supported manifest evidence, or explicit user declarations, identify an application/tooling stack.
- **Documentation:** the inspected file set contains documentation/metadata or known documentation-generator inputs without contrary evidence.
- **Unknown:** unsupported files, missing evidence, unreadable input or incomplete inspection prevent a reliable classification. A README alone does not override application/unknown evidence.

Unknown repositories retain portable guidance and the local Python tools. Auto mode does not download RTK or Repomix for unknown input. An explicit preset or manual declaration can change the plan. Agent instructions alone do not make a repository documentary.

`propose` and `context` expose classification, reasons, relevant source filenames and inspection limits. They do not read implementation contents to guess a stack. Manual provenance and observed manifest declarations remain distinguishable.

## Recognized static evidence

| Ecosystem | Manifest evidence | Important limit |
|---|---|---|
| JavaScript/TypeScript | package.json, supported lockfiles/configs | Unlisted frameworks may have generic guidance only |
| Python | pyproject.toml, requirements.txt, uv/Poetry locks | Executable setup.py is not evaluated |
| Rust / Go | Cargo.toml/Cargo.lock, go.mod/go.sum | Dependency and compiler versions are distinct |
| JVM / .NET | Maven/Gradle manifests, csproj/global.json | Only statically resolvable declarations |
| Ruby / PHP | Gemfile/lock, composer.json/lock | No project code is executed |
| C/C++ | CMakeLists.txt, meson.build, conanfile.txt | Computed variables and Python Conan recipes remain unresolved |
| Dart / Flutter | pubspec.yaml | Conservative indentation/scalar subset, not arbitrary YAML evaluation |
| Swift | Package.swift | Literal declarations only; tools header is swift-tools evidence, not an exact compiler version |
| Elixir / Phoenix | mix.exs | Literal declarations only; macros/functions are not evaluated |
| R | DESCRIPTION, renv.lock | Package, R runtime constraint and renv versions stay separate |
| Julia | Project.toml | Project version is not the Julia language version |
| Infrastructure | Terraform/container/CI manifests | Use explicit scopes where no package boundary is available |

Directory package boundaries come from the shared adapter registry. For example, CMake and React packages are profiled independently in one repository. Nested Git repositories, submodules and worktrees form excluded boundaries and should be profiled independently. Exclusions are reported.

## Unsupported or custom projects

Use [auto-skills.toml](configuration.md) to declare existing workspace paths, intended technology constraints, repository kind and supported guide roles. User configuration is data, not executable hooks. Unknown technology names remain visible as capability gaps rather than manufacturing a matching guide.

Automatic discovery and version compatibility remain conservative heuristics. A bundled fallback does not demonstrate an eligible upstream guide exists, and a declared constraint does not certify installed hardware/toolchain behavior.

## Bounds

Manifest depth is limited to 8 directories, ordinary manifests to 512,000 bytes, supported locks to 16 MiB and the inventory to 2,000 manifests. Filename-only classification uses a 10,000-entry budget. Truncated/unreadable/redirected evidence is reported; an exhausted manifest-count budget fails with an actionable message. No unsupported project is silently certified as fully understood.

## Extending coverage

Add an inert `Adapter` entry in `adapters.py` with recognized filenames, package boundaries and an extractor returning `Evidence` records. Keep language, build-tool and package versions distinct. Add bundled guidance and slot mapping when useful. Existing legacy extractors remain in `profile.py`; their inventory/boundaries use the same registry.

Require tests for direct declarations, malformed/dynamic expressions, misleading comments, mixed-language scopes, unrelated-guide exclusions and no target writes. Validate against a pinned public manifest snapshot with attribution, then record limitations. A manifest snapshot verifies static extraction, not an entire upstream build or every branch of that repository.

The [14-repository pinned matrix](../reports/real-repositories.md) exercises upstream manifest extracts across the listed ecosystems. Run `python tools/verify_real_repositories.py` offline to verify copied manifest/license hashes, guide coverage and scope isolation. `--refresh` is an explicit network operation that resolves new upstream revisions; it is not part of ordinary profiling or CI.
