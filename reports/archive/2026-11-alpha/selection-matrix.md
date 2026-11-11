# Simulations de dépôts Auto-Skills

Dépôts fictifs, profilage et sélection réels, aucune installation dans les dépôts simulés.
Mode hors ligne : catalogue intégré uniquement. La colonne extérieure vide ne mesure pas la couverture GitHub.
Les registres synthétiques servent uniquement aux tests adversariaux séparés ci-dessous.

| Dépôt simulé | Skills intérieurs (intégrés) | Skills extérieurs (GitHub) | Plugins/outils proposés | Cohérence |
|---|---|---|---|---|
| Next.js / React / Prisma / PostgreSQL | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `containers`, `language-javascript`, `framework-next`, `database-postgres`, `orm-prisma`, `framework-react`, `ui-components`, `language-typescript`, `test-vitest`, `e2e-testing`, `static-analysis` | Non recherchés (hors ligne) | `token-run`, `repo-map`, `rtk`, `repomix` | Cohérent |
| Vue / Vite / Vitest / Tailwind | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `language-javascript`, `ui-components`, `test-testing-library`, `language-typescript`, `build-vite`, `test-vitest`, `framework-vue`, `static-analysis` | Non recherchés (hors ligne) | `token-run`, `repo-map`, `rtk`, `repomix` | Cohérent |
| FastAPI / SQLAlchemy / PostgreSQL | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `containers`, `framework-fastapi`, `database-postgres`, `language-python`, `orm-sqlalchemy`, `static-analysis` | Non recherchés (hors ligne) | `token-run`, `repo-map`, `rtk` | Cohérent |
| Django / Redis / PostgreSQL | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `framework-django`, `containers`, `database-postgres`, `language-python`, `database-redis` | Non recherchés (hors ligne) | `token-run`, `repo-map`, `rtk` | Cohérent |
| Go / Gin / GORM / PostgreSQL | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `framework-gin`, `language-go`, `orm-gorm`, `database-postgres` | Non recherchés (hors ligne) | `token-run`, `repo-map`, `rtk` | Cohérent |
| Rust / Axum / Tokio / SQLite | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `framework-axum`, `language-rust`, `database-sqlite` | Non recherchés (hors ligne) | `token-run`, `repo-map`, `rtk` | Cohérent |
| Tauri / React / MIDI / OSC / ASIO / VST | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `language-javascript`, `framework-react`, `language-rust`, `framework-tauri`, `language-typescript`, `build-vite`, `test-vitest`, `static-analysis`, `unit-testing` (src-tauri), `build` (src-tauri), `realtime-audio` (src-tauri), `audio-asio` (src-tauri), `audio-cpal` (src-tauri), `midi` (src-tauri), `osc` (src-tauri), `rtp-midi` (src-tauri), `language-rust` (src-tauri), `framework-tauri` (src-tauri), `audio-plugin-vst` (src-tauri), `native-windows` (src-tauri), `process-workers` (src-tauri) | Non recherchés (hors ligne) | `token-run`, `repo-map`, `rtk`, `repomix` | Cohérent |
| PHP / Laravel | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `framework-laravel`, `language-php` | Non recherchés (hors ligne) | `token-run`, `repo-map`, `rtk` | Cohérent |
| Monorepo React 18 + React 19 + FastAPI | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `unit-testing` (apps/legacy), `build` (apps/legacy), `language-javascript` (apps/legacy), `framework-react` (apps/legacy), `language-typescript` (apps/legacy), `static-analysis` (apps/legacy), `unit-testing` (apps/web), `build` (apps/web), `language-javascript` (apps/web), `framework-next` (apps/web), `framework-react` (apps/web), `language-typescript` (apps/web), `test-vitest` (apps/web), `static-analysis` (apps/web), `unit-testing` (services/api), `build` (services/api), `framework-fastapi` (services/api), `language-python` (services/api) | Non recherchés (hors ligne) | `token-run`, `repo-map`, `rtk`, `repomix` | Cohérent |
| CLI TypeScript + dépendances transitives trompeuses | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `language-javascript`, `language-typescript`, `static-analysis` | Non recherchés (hors ligne) | `token-run`, `repo-map`, `rtk`, `repomix` | Cohérent |
| Java / Spring Boot / Maven | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `language-java`, `framework-spring` | Non recherchés (hors ligne) | `token-run`, `repo-map`, `rtk` | Cohérent |
| .NET / ASP.NET Core / EF Core / SQL Server | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `framework-aspnet`, `language-dotnet`, `orm-entityframework`, `database-sqlserver` | Non recherchés (hors ligne) | `token-run`, `repo-map`, `rtk` | Cohérent |
| Solidity / Hardhat / TypeScript | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `test-hardhat`, `language-javascript`, `language-solidity`, `language-typescript`, `static-analysis` | Non recherchés (hors ligne) | `token-run`, `repo-map`, `rtk`, `repomix` | Cohérent |
| Documentation seule | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `documentation` | Non recherchés (hors ligne) | `token-run`, `repo-map` | Cohérent |
| Node / pg / Redis sans serveur déclaré | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `language-javascript`, `database-postgres`, `database-redis` | Non recherchés (hors ligne) | `token-run`, `repo-map`, `rtk`, `repomix` | Cohérent |
| Python / psycopg / Redis sans serveur déclaré | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `database-postgres`, `language-python`, `database-redis` | Non recherchés (hors ligne) | `token-run`, `repo-map`, `rtk` | Cohérent |
| Rust / rusqlite sans moteur versionné | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `language-rust`, `database-sqlite` | Non recherchés (hors ligne) | `token-run`, `repo-map`, `rtk` | Cohérent |
| React 19.2 / TypeScript : APIs modernes | `token-output-compression`, `token-context-pruning`, `token-reasoning`, `token-prompt-cache`, `token-cli-wrapper`, `architecture`, `unit-testing`, `security`, `performance`, `refactoring`, `ci-cd`, `build`, `documentation`, `language-javascript`, `framework-react`, `language-typescript`, `static-analysis` | Non recherchés (hors ligne) | `token-run`, `repo-map`, `rtk`, `repomix` | Cohérent |

## Qualité et pertinence des skills extérieurs

Ces contrôles sont des heuristiques de sélection, pas une certification de qualité : compatibilité déclarée, technologies détectées, dépendances disponibles, concision, provenance et score. Le commit fixe la version examinée.

| Dépôt / workspace | Skill extérieur | Source épinglée | Compatibilité / technologies | Motif / score |
|---|---|---|---|---|
| — | Aucun résultat externe vérifié pendant cette exécution | — | — | — |

## Lacunes et diagnostics

- **Next.js / React / Prisma / PostgreSQL** : Versions pg (client) et PostgreSQL (serveur) distinctes, vérifiées séparément.
- **FastAPI / SQLAlchemy / PostgreSQL** : Versions psycopg (client) et PostgreSQL (serveur) distinctes, vérifiées séparément.
- **Django / Redis / PostgreSQL** : Clients Python et serveurs Redis/PostgreSQL ont des versions indépendantes.
- **Go / Gin / GORM / PostgreSQL** : La base est reconnue via pgx ; sa version serveur reste inconnue.
- **Monorepo React 18 + React 19 + FastAPI** : React 18 et React 19 reçoivent des sélections distinctes par workspace.
- **Java / Spring Boot / Maven** : Spring Boot et Java sont extraits du POM.
- **.NET / ASP.NET Core / EF Core / SQL Server** : ASP.NET et EF Core sont identifiés ; la version du serveur SQL reste inconnue.
- **Solidity / Hardhat / TypeScript** : Solidity et Hardhat sont couverts ; aucun skill blockchain ne doit occuper un slot token-saver.
- **Documentation seule** : Le socle et les outils sont réduits pour la documentation.
- **Node / pg / Redis sans serveur déclaré** : Les versions pg et redis sont des versions de clients ; moteurs inconnus.
- **React 19.2 / TypeScript : APIs modernes** : Contrôle positif React 19.2 ; les cas React 18 et 19.0 restent distincts et ne doivent pas accepter des exemples limités aux nouvelles APIs.

## Registre synthétique : cas adversariaux (aucune recommandation externe)

| Cas | Vérification |
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

## Critères CI

La CI bloque toute nouvelle absence de slot attendu, slot incohérent, confusion pilote/serveur, ambiguïté non autorisée, duplication par workspace ou modification d’un dépôt simulé. Les lacunes autorisées sont suivies par scénario dans les entrées JSON ; elles sont actuellement vides pour les stacks annoncées.
Le contrôle GitHub en direct est séparé des tests déterministes : une indisponibilité réseau ne valide ni n’invalide la qualité d’un skill absent.
