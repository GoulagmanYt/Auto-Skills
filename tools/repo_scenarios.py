"""Small handwritten repository fixtures and independent coverage expectations."""

import json
from dataclasses import dataclass, field


def node(dependencies, dev=None):
    return json.dumps(
        {
            "name": "simulation",
            "private": True,
            "dependencies": dependencies,
            "devDependencies": dev or {},
            "scripts": {"test": "fixture-only"},
        },
        indent=2,
    )


def python_project(dependencies):
    return (
        '[project]\nname="simulation"\nversion="0.1.0"\nrequires-python=">=3.11,<3.14"\n'
        + "dependencies="
        + json.dumps(dependencies)
        + "\n"
    )


@dataclass(frozen=True)
class Scenario:
    slug: str
    title: str
    files: dict[str, str]
    required: frozenset[str]
    forbidden: frozenset[str] = field(default_factory=frozenset)
    known_gaps: frozenset[str] = field(default_factory=frozenset)
    allowed_multiple: frozenset[str] = field(default_factory=frozenset)
    note: str = ""


def scenario(slug, title, files, required, forbidden=(), gaps=(), multiple=(), note=""):
    return Scenario(
        slug,
        title,
        files,
        frozenset(required),
        frozenset(forbidden),
        frozenset(gaps),
        frozenset(multiple),
        note,
    )


WEB_FORBIDDEN = {"language-rust", "framework-fastapi", "audio-asio", "audio-plugin-vst"}
PY_FORBIDDEN = {"framework-react", "framework-next", "ui-components", "language-rust"}

SCENARIOS = [
    scenario(
        "next-commerce",
        "Next.js / React / Prisma / PostgreSQL",
        {
            "package.json": node(
                {
                    "next": "^15.2.0",
                    "react": "^19.0.0",
                    "@prisma/client": "^6.0.0",
                    "pg": "^8.13.0",
                },
                {
                    "typescript": "^5.7.0",
                    "tailwindcss": "^4.0.0",
                    "vitest": "^3.0.0",
                    "@playwright/test": "^1.50.0",
                },
            ),
            "compose.yml": "services:\n  db:\n    image: postgres:16\n",
        },
        {
            "language-typescript",
            "framework-next",
            "framework-react",
            "orm-prisma",
            "database-postgres",
            "e2e-testing",
            "test-vitest",
            "ui-components",
            "containers",
        },
        WEB_FORBIDDEN,
        note="Versions pg (client) et PostgreSQL (serveur) distinctes, vérifiées séparément.",
    ),
    scenario(
        "vue-dashboard",
        "Vue / Vite / Vitest / Tailwind",
        {
            "package.json": node(
                {"vue": "^3.5.0"},
                {
                    "typescript": "^5.7.0",
                    "vite": "^6.0.0",
                    "vitest": "^3.0.0",
                    "@testing-library/vue": "^8.1.0",
                    "tailwindcss": "^4.0.0",
                },
            ),
            "vite.config.ts": "export default {};\n",
        },
        {
            "framework-vue",
            "build-vite",
            "test-vitest",
            "test-testing-library",
            "ui-components",
            "language-typescript",
        },
        {"framework-react", "framework-next", "language-rust"},
    ),
    scenario(
        "fastapi-api",
        "FastAPI / SQLAlchemy / PostgreSQL",
        {
            "pyproject.toml": python_project(
                [
                    "fastapi>=0.115,<1",
                    "sqlalchemy>=2,<3",
                    "psycopg>=3,<4",
                    "pytest>=8,<9",
                    "ruff>=0.9,<1",
                ]
            ),
            "compose.yml": "services:\n  db:\n    image: postgres:16\n",
        },
        {
            "language-python",
            "framework-fastapi",
            "orm-sqlalchemy",
            "database-postgres",
            "static-analysis",
            "containers",
        },
        PY_FORBIDDEN,
        note="Versions psycopg (client) et PostgreSQL (serveur) distinctes, vérifiées séparément.",
    ),
    scenario(
        "django-service",
        "Django / Redis / PostgreSQL",
        {
            "pyproject.toml": python_project(
                ["django>=5.2,<6", "psycopg>=3,<4", "redis>=5,<6", "pytest>=8,<9"]
            ),
            "compose.yml": "services:\n  db:\n    image: postgres:16\n  cache:\n    image: redis:7\n",
        },
        {
            "language-python",
            "framework-django",
            "database-postgres",
            "database-redis",
            "containers",
        },
        PY_FORBIDDEN,
        note="Clients Python et serveurs Redis/PostgreSQL ont des versions indépendantes.",
    ),
    scenario(
        "go-gin-service",
        "Go / Gin / GORM / PostgreSQL",
        {
            "go.mod": "module example.invalid/simulation\n\ngo 1.23\n\nrequire (\n github.com/gin-gonic/gin v1.10.0\n gorm.io/gorm v1.25.0\n github.com/jackc/pgx/v5 v5.7.0\n)\n",
        },
        {"language-go", "framework-gin", "orm-gorm", "database-postgres"},
        {"language-python", "framework-react", "audio-asio"},
        note="La base est reconnue via pgx ; sa version serveur reste inconnue.",
    ),
    scenario(
        "rust-web-service",
        "Rust / Axum / Tokio / SQLite",
        {
            "Cargo.toml": '[package]\nname="simulation"\nversion="0.1.0"\nedition="2021"\n[dependencies]\naxum="0.8"\ntokio={version="1.43",features=["rt-multi-thread","net"]}\nrusqlite="0.32"\n',
            "rust-toolchain.toml": '[toolchain]\nchannel="1.85.0"\n',
        },
        {"language-rust", "framework-axum", "database-sqlite"},
        {"framework-react", "realtime-audio", "midi", "audio-asio", "process-workers"},
    ),
    scenario(
        "desktop-midi",
        "Tauri / React / MIDI / OSC / ASIO / VST",
        {
            "package.json": node(
                {"react": "^19.0.0", "@tauri-apps/api": "^2.11.0"},
                {"typescript": "^5.9.0", "vite": "^8.0.0", "vitest": "^3.0.0"},
            ),
            "rust-toolchain.toml": '[toolchain]\nchannel="1.90.0"\n',
            "src-tauri/Cargo.toml": '[package]\nname="simulation"\nversion="0.1.0"\nedition="2021"\n[dependencies]\ntauri="2.11.5"\ncpal={version="0.18.2",features=["asio"]}\nmidir="0.11"\nrosc="0.11"\nrtpmidi="0.4"\nvst="0.4"\nwindows={version="0.62",features=["Win32_System_JobObjects"]}\n',
        },
        {
            "framework-tauri",
            "framework-react",
            "language-rust",
            "realtime-audio",
            "audio-asio",
            "midi",
            "osc",
            "rtp-midi",
            "audio-plugin-vst",
            "native-windows",
            "process-workers",
        },
        {"framework-next", "orm-prisma", "database-postgres"},
    ),
    scenario(
        "laravel-api",
        "PHP / Laravel",
        {
            "composer.json": json.dumps(
                {
                    "require": {"php": "^8.2", "laravel/framework": "^11.0"},
                    "require-dev": {"phpunit/phpunit": "^11.0"},
                }
            ),
        },
        {"language-php", "framework-laravel"},
        {"framework-react", "language-python", "database-postgres"},
    ),
    scenario(
        "mixed-monorepo",
        "Monorepo React 18 + React 19 + FastAPI",
        {
            "apps/legacy/package.json": node({"react": "^18.3.0"}, {"typescript": "^5.7.0"}),
            "apps/web/package.json": node(
                {"react": "^19.0.0", "next": "^15.2.0"},
                {"typescript": "^5.7.0", "vitest": "^3.0.0"},
            ),
            "services/api/pyproject.toml": python_project(["fastapi>=0.115,<1", "pytest>=8,<9"]),
        },
        {
            "framework-react",
            "framework-next",
            "language-typescript",
            "framework-fastapi",
            "language-python",
        },
        {"audio-asio", "framework-vue"},
        multiple={"react"},
        note="React 18 et React 19 reçoivent des sélections distinctes par workspace.",
    ),
    scenario(
        "lockfile-decoy",
        "CLI TypeScript + dépendances transitives trompeuses",
        {
            "package.json": node({}, {"typescript": "^5.9.0"}),
            "package-lock.json": json.dumps(
                {
                    "lockfileVersion": 3,
                    "packages": {
                        "": {"name": "simulation"},
                        "node_modules/react": {"version": "19.0.0"},
                        "node_modules/next": {"version": "15.0.0"},
                        "node_modules/@prisma/client": {"version": "6.0.0"},
                    },
                }
            ),
            "src/never-read.tsx": "throw new Error('This source mentions React Next Prisma but must not be profiled');\n",
        },
        {"language-javascript", "language-typescript", "static-analysis"},
        {"framework-react", "framework-next", "orm-prisma", "database-postgres"},
    ),
    scenario(
        "spring-api",
        "Java / Spring Boot / Maven",
        {
            "pom.xml": "<project><modelVersion>4.0.0</modelVersion><parent><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-parent</artifactId><version>3.4.0</version></parent><properties><java.version>17</java.version></properties><dependencies><dependency><groupId>org.springframework.boot</groupId><artifactId>spring-boot-starter-web</artifactId></dependency></dependencies></project>",
        },
        {"language-java", "framework-spring"},
        {"framework-react", "language-python"},
        note="Spring Boot et Java sont extraits du POM.",
    ),
    scenario(
        "aspnet-api",
        ".NET / ASP.NET Core / EF Core / SQL Server",
        {
            "Api.csproj": '<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup><ItemGroup><PackageReference Include="Microsoft.EntityFrameworkCore.SqlServer" Version="8.0.0" /></ItemGroup></Project>',
        },
        {"language-dotnet", "framework-aspnet", "orm-entityframework", "database-sqlserver"},
        {"framework-react", "language-python"},
        note="ASP.NET et EF Core sont identifiés ; la version du serveur SQL reste inconnue.",
    ),
    scenario(
        "solidity-project",
        "Solidity / Hardhat / TypeScript",
        {
            "package.json": node(
                {"ethers": "^6.13.0"}, {"hardhat": "^2.22.0", "typescript": "^5.7.0"}
            ),
            "foundry.toml": '[profile.default]\nsolc_version="0.8.28"\n',
        },
        {"language-typescript", "language-solidity", "test-hardhat"},
        {"framework-react", "framework-next"},
        note="Solidity et Hardhat sont couverts ; aucun skill blockchain ne doit occuper un slot token-saver.",
    ),
    scenario(
        "documentation-only",
        "Documentation seule",
        {
            "README.md": "# Documentation\nThis repository contains only documentation.\n",
        },
        {"documentation"},
        {"language-python", "language-javascript", "framework-react", "framework-tauri"},
        note="Le socle et les outils sont réduits pour la documentation.",
    ),
]

SCENARIOS.extend(
    [
        scenario(
            "driver-only-node",
            "Node / pg / Redis sans serveur déclaré",
            {"package.json": node({"pg": "^8.13.0", "redis": "^5.0.0"})},
            {"language-javascript", "database-postgres", "database-redis"},
            {"framework-react", "containers"},
            note="Les versions pg et redis sont des versions de clients ; moteurs inconnus.",
        ),
        scenario(
            "driver-only-python",
            "Python / psycopg / Redis sans serveur déclaré",
            {"pyproject.toml": python_project(["psycopg>=3,<4", "redis>=5,<6"])},
            {"language-python", "database-postgres", "database-redis"},
            {"framework-react", "framework-fastapi", "containers"},
        ),
        scenario(
            "driver-only-sqlite",
            "Rust / rusqlite sans moteur versionné",
            {
                "Cargo.toml": '[package]\nname="sqlite-tool"\nversion="0.1.0"\n[dependencies]\nrusqlite="0.32"\n'
            },
            {"language-rust", "database-sqlite"},
            {"framework-axum", "containers"},
        ),
    ]
)

SCENARIOS.append(
    scenario(
        "react-19-2",
        "React 19.2 / TypeScript : APIs modernes",
        {"package.json": node({"react": "^19.2.0"}, {"typescript": "^5.9.0"})},
        {"language-javascript", "language-typescript", "framework-react", "static-analysis"},
        {"framework-next", "framework-vue", "language-python"},
        note="Contrôle positif React 19.2 ; les cas React 18 et 19.0 restent distincts et ne doivent pas accepter des exemples limités aux nouvelles APIs.",
    )
)
