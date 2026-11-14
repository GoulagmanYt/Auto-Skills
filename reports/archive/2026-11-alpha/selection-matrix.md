# Auto-Skills repository simulations

Synthetic repositories, real profiling and selection, no installation in the simulated repositories.
Offline mode: built-in catalog only. The empty external column does not measure GitHub coverage.
Synthetic registries are used only for the separate adversarial tests below.

| Simulated repository | Bundled skills | External skills (GitHub) | Proposed plugins/tools | Consistency |
|---|---|---|---|---|
| Next.js / React / Prisma / PostgreSQL | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `containers`, `language-javascript`, `framework-next`, `database-postgres`, `orm-prisma`, `framework-react`, `ui-components`, `language-typescript`, `test-vitest`, `e2e-testing`, `static-analysis` | Not searched (offline) | `token-run`, `repo-map`, `rtk`, `repomix` | Consistent |
| Vue / Vite / Vitest / Tailwind | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `language-javascript`, `ui-components`, `test-testing-library`, `language-typescript`, `build-vite`, `test-vitest`, `framework-vue`, `static-analysis` | Not searched (offline) | `token-run`, `repo-map`, `rtk`, `repomix` | Consistent |
| FastAPI / SQLAlchemy / PostgreSQL | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `containers`, `framework-fastapi`, `database-postgres`, `language-python`, `orm-sqlalchemy`, `static-analysis` | Not searched (offline) | `token-run`, `repo-map`, `rtk` | Consistent |
| Django / Redis / PostgreSQL | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `framework-django`, `containers`, `database-postgres`, `language-python`, `database-redis` | Not searched (offline) | `token-run`, `repo-map`, `rtk` | Consistent |
| Go / Gin / GORM / PostgreSQL | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `framework-gin`, `language-go`, `orm-gorm`, `database-postgres` | Not searched (offline) | `token-run`, `repo-map`, `rtk` | Consistent |
| Rust / Axum / Tokio / SQLite | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `framework-axum`, `language-rust`, `database-sqlite` | Not searched (offline) | `token-run`, `repo-map`, `rtk` | Consistent |
| Tauri / React / MIDI / OSC / ASIO / VST | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `language-javascript`, `framework-react`, `language-rust`, `framework-tauri`, `language-typescript`, `build-vite`, `test-vitest`, `static-analysis`, `unit-testing` (src-tauri), `build` (src-tauri), `realtime-audio` (src-tauri), `audio-asio` (src-tauri), `audio-cpal` (src-tauri), `midi` (src-tauri), `osc` (src-tauri), `rtp-midi` (src-tauri), `language-rust` (src-tauri), `framework-tauri` (src-tauri), `audio-plugin-vst` (src-tauri), `native-windows` (src-tauri), `process-workers` (src-tauri) | Not searched (offline) | `token-run`, `repo-map`, `rtk`, `repomix` | Consistent |
| PHP / Laravel | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `framework-laravel`, `language-php` | Not searched (offline) | `token-run`, `repo-map`, `rtk` | Consistent |
| Monorepo React 18 + React 19 + FastAPI | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `unit-testing` (apps/legacy), `build` (apps/legacy), `language-javascript` (apps/legacy), `framework-react` (apps/legacy), `language-typescript` (apps/legacy), `static-analysis` (apps/legacy), `unit-testing` (apps/web), `build` (apps/web), `language-javascript` (apps/web), `framework-next` (apps/web), `framework-react` (apps/web), `language-typescript` (apps/web), `test-vitest` (apps/web), `static-analysis` (apps/web), `unit-testing` (services/api), `build` (services/api), `framework-fastapi` (services/api), `language-python` (services/api) | Not searched (offline) | `token-run`, `repo-map`, `rtk`, `repomix` | Consistent |
| TypeScript CLI + misleading transitive dependencies | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `language-javascript`, `language-typescript`, `static-analysis` | Not searched (offline) | `token-run`, `repo-map`, `rtk`, `repomix` | Consistent |
| Java / Spring Boot / Maven | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `language-java`, `framework-spring` | Not searched (offline) | `token-run`, `repo-map`, `rtk` | Consistent |
| .NET / ASP.NET Core / EF Core / SQL Server | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `framework-aspnet`, `language-dotnet`, `orm-entityframework`, `database-sqlserver` | Not searched (offline) | `token-run`, `repo-map`, `rtk` | Consistent |
| Solidity / Hardhat / TypeScript | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `test-hardhat`, `language-javascript`, `language-solidity`, `language-typescript`, `static-analysis` | Not searched (offline) | `token-run`, `repo-map`, `rtk`, `repomix` | Consistent |
| Documentation only | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `documentation` | Not searched (offline) | `token-run`, `repo-map` | Consistent |
| Node / pg / Redis without a declared server | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `language-javascript`, `database-postgres`, `database-redis` | Not searched (offline) | `token-run`, `repo-map`, `rtk`, `repomix` | Consistent |
| Python / psycopg / Redis without a declared server | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `database-postgres`, `language-python`, `database-redis` | Not searched (offline) | `token-run`, `repo-map`, `rtk` | Consistent |
| Rust / rusqlite without a versioned engine | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `language-rust`, `database-sqlite` | Not searched (offline) | `token-run`, `repo-map`, `rtk` | Consistent |
| React 19.2 / TypeScript: modern APIs | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `language-javascript`, `framework-react`, `language-typescript`, `static-analysis` | Not searched (offline) | `token-run`, `repo-map`, `rtk`, `repomix` | Consistent |

## External skill quality and relevance

These checks are selection heuristics, not a quality certification: declared compatibility, detected technologies, available dependencies, concision, provenance and score. The commit pins the reviewed version.

| Repository / workspace | External skill | Pinned source | Compatibility / technologies | Reason / score |
|---|---|---|---|---|
| — | No external result verified during this run | — | — | — |

## Gaps and diagnostics

- **Next.js / React / Prisma / PostgreSQL**: pg (client) and PostgreSQL (server) versions are distinct and checked separately.
- **FastAPI / SQLAlchemy / PostgreSQL**: psycopg (client) and PostgreSQL (server) versions are distinct and checked separately.
- **Django / Redis / PostgreSQL**: Python clients and Redis/PostgreSQL servers have independent versions.
- **Go / Gin / GORM / PostgreSQL**: The database is recognized through pgx; its server version remains unknown.
- **Monorepo React 18 + React 19 + FastAPI**: React 18 and React 19 receive separate selections for each workspace.
- **Java / Spring Boot / Maven**: Spring Boot and Java are extracted from the POM.
- **.NET / ASP.NET Core / EF Core / SQL Server**: ASP.NET and EF Core are identified; the SQL Server version remains unknown.
- **Solidity / Hardhat / TypeScript**: Solidity and Hardhat are covered; no blockchain skill should occupy a token-saver slot.
- **Documentation only**: The baseline and tools are reduced for documentation.
- **Node / pg / Redis without a declared server**: pg and redis versions refer to clients; engine versions are unknown.
- **React 19.2 / TypeScript: modern APIs**: React 19.2 positive control; React 18 and 19.0 cases remain distinct and must reject examples restricted to newer APIs.

## Synthetic registry: adversarial cases (no external recommendations)

| Case | Verification |
|---|---|
| `react-version` | OK |
| `notion-out-of-scope` | OK |
| `blockchain-is-not-token-saving` | OK |
| `vue-rejects-react-skill` | OK |
| `orm-mismatch` | OK |
| `monorepo-workspace-specific-versions` | OK |
| `missing-executable` | OK |
| `audit-context-is-not-pruning` | OK |
| `game-performance-is-not-api-performance` | OK |
| `documentation-rejects-code-only-context` | OK |
| `react-modern-api-18-3-0` | OK |
| `react-modern-api-19-0-0` | OK |
| `react-modern-api-19-2-0` | OK |
| `react-native-is-not-react-web` | OK |
| `registry-outage` | OK |

## CI criteria

CI blocks any newly missing expected slot, inconsistent slot, driver/server confusion, unapproved ambiguity, duplicate within a workspace or modification of a simulated repository. Allowed gaps are tracked per scenario in the JSON inputs; they are currently empty for the advertised stacks.
The live GitHub check is separate from deterministic tests: a network outage neither validates nor invalidates the quality of a missing skill.
