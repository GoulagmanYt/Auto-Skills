"""Read only manifests/configuration, never implementation files or secret values."""

import hashlib
import json
import os
import re
import shutil
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import adapters

SKIP = {
    ".git",
    ".codex",
    ".agents",
    "node_modules",
    "vendor",
    ".venv",
    "venv",
    "dist",
    "build",
    "target",
    ".cargo-target",
    "coverage",
    ".next",
    "__pycache__",
}
BASE_SLOTS = [
    "token-output-compression",
    "token-context-pruning",
    "token-reasoning",
    "token-prompt-cache",
    "token-cli-wrapper",
    "architecture",
    "unit-testing",
    "security",
    "performance",
    "refactoring",
    "ci-cd",
    "build",
    "documentation",
]
TECH_SLOTS = {
    "react": "framework-react",
    "next": "framework-next",
    "vue": "framework-vue",
    "nuxt": "framework-nuxt",
    "svelte": "framework-svelte",
    "angular": "framework-angular",
    "fastapi": "framework-fastapi",
    "django": "framework-django",
    "flask": "framework-flask",
    "express": "framework-express",
    "nestjs": "framework-nestjs",
    "axum": "framework-axum",
    "gin": "framework-gin",
    "rails": "framework-rails",
    "laravel": "framework-laravel",
    "prisma": "orm-prisma",
    "drizzle": "orm-drizzle",
    "sqlalchemy": "orm-sqlalchemy",
    "typeorm": "orm-typeorm",
    "diesel": "orm-diesel",
    "gorm": "orm-gorm",
    "postgres": "database-postgres",
    "mysql": "database-mysql",
    "sqlite": "database-sqlite",
    "mongodb": "database-mongodb",
    "redis": "database-redis",
    "docker": "containers",
    "terraform": "infrastructure",
    "tailwindcss": "ui-components",
    "shadcn": "ui-components",
    "tauri": "framework-tauri",
    "tauri-api": "framework-tauri",
    "tauri-cli": "framework-tauri",
    "vite": "build-vite",
    "vitest": "test-vitest",
    "jest": "test-jest",
    "testing-library": "test-testing-library",
    "zustand": "frontend-state",
    "redux": "frontend-state",
    "react-router": "frontend-routing",
    "tanstack-router": "frontend-routing",
    "spring": "framework-spring",
    "aspnet": "framework-aspnet",
    "entityframework": "orm-entityframework",
    "sqlserver": "database-sqlserver",
    "hardhat": "test-hardhat",
}
DOMAIN_SLOTS = {
    "cpal": ("realtime-audio", "audio-cpal"),
    "portaudio": ("realtime-audio",),
    "jack": ("realtime-audio",),
    "asio": ("realtime-audio", "audio-asio"),
    "asio-sys": ("realtime-audio", "audio-asio"),
    "midir": ("midi",),
    "midi2": ("midi",),
    "rtp-midi": ("midi", "rtp-midi"),
    "rtpmidi": ("midi", "rtp-midi"),
    "rosc": ("osc",),
    "osc": ("osc",),
    "vst": ("audio-plugin-vst",),
    "vst3": ("audio-plugin-vst",),
    "vst3-sys": ("audio-plugin-vst",),
    "nih_plug": ("audio-plugin-vst",),
    "windows": ("native-windows",),
    "windows-sys": ("native-windows",),
    "winapi": ("native-windows",),
    "tauri-plugin-shell": ("process-workers",),
    "process-workers": ("process-workers",),
}
# These package names are meaningful only as Python distribution declarations.
# GPIO Zero also supports mock/remote pins, so it alone is not Pi platform evidence.
PYTHON_DOMAIN_SLOTS = {
    "mido": ("midi", "midi-python"),
    "python-rtmidi": ("midi", "midi-python"),
    "rpi-ws281x": ("led-ws281x", "platform-raspberry-pi"),
    "rpi-gpio": ("gpio-python", "platform-raspberry-pi"),
    "gpiozero": ("gpio-python",),
}
ALIASES = {
    "@prisma/client": "prisma",
    "drizzle-orm": "drizzle",
    "@angular/core": "angular",
    "@nestjs/core": "nestjs",
    "@playwright/test": "playwright",
    "@tauri-apps/api": "tauri-api",
    "@tauri-apps/cli": "tauri-cli",
    "@testing-library/react": "testing-library",
    "@testing-library/dom": "testing-library",
    "@testing-library/vue": "testing-library",
    "@reduxjs/toolkit": "redux",
    "react-redux": "redux",
    "react-router-dom": "react-router",
    "@tanstack/react-router": "tanstack-router",
    "github.com/gin-gonic/gin": "gin",
    "gorm.io/gorm": "gorm",
}

# Package releases describe client APIs, never the deployed database version.
DATABASE_CLIENTS = {
    "pg": "postgres",
    "postgres": "postgres",
    "psycopg": "postgres",
    "psycopg2": "postgres",
    "psycopg2-binary": "postgres",
    "github.com/jackc/pgx/v5": "postgres",
    "org.postgresql:postgresql": "postgres",
    "pymongo": "mongodb",
    "redis": "redis",
    "rusqlite": "sqlite",
    "better-sqlite3": "sqlite",
    "microsoft.entityframeworkcore.sqlserver": "sqlserver",
    "microsoft.data.sqlclient": "sqlserver",
    "system.data.sqlclient": "sqlserver",
}


@dataclass
class Profile:
    technologies: dict[str, str] = field(default_factory=dict)
    slots: list[str] = field(default_factory=lambda: list(BASE_SLOTS))
    manifests: list[str] = field(default_factory=list)
    commands: dict[str, dict[str, str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    technology_sources: dict[str, list[dict]] = field(default_factory=dict)
    resolved_versions: dict[str, list[str]] = field(default_factory=dict)
    slot_technologies: dict[str, list[str]] = field(default_factory=dict)
    available_tools: list[str] = field(default_factory=list)
    components: list[dict] = field(default_factory=list)
    repository_kind: str = "auto"
    kind_source: dict | None = None
    manual_configuration: dict = field(default_factory=dict)
    diagnostics: list[dict] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


LOCK_NAMES = adapters.lock_names()
MANIFEST_LIMIT = 512_000
LOCK_LIMIT = 16 * 1024 * 1024


def manifest_paths(root: Path, *, diagnostics=None):
    """Yield bounded manifest paths; report excluded boundaries when requested."""
    root = Path(root).resolve()
    count = 0

    def excluded(code, path, message):
        if diagnostics is not None:
            diagnostics.append(
                {"code": code, "path": path.relative_to(root).as_posix(), "message": message}
            )

    for directory, dirs, files in os.walk(root, followlinks=False):
        current = Path(directory)
        if current != root and (current / ".git").exists():
            excluded(
                "submodule-boundary",
                current,
                "Nested Git repository/worktree boundary excluded; profile it independently.",
            )
            dirs[:] = []
            continue
        safe_dirs = []
        for dirname in sorted(dirs):
            if dirname in SKIP:
                continue
            candidate = current / dirname
            try:
                redirected = candidate.is_symlink() or candidate.resolve() != candidate.absolute()
            except (OSError, RuntimeError):
                redirected = True
            if redirected:
                excluded(
                    "manifest-directory-redirect",
                    candidate,
                    "Redirected directory excluded before traversal.",
                )
            else:
                safe_dirs.append(dirname)
        dirs[:] = safe_dirs
        rel_dir = current.relative_to(root)
        if len(rel_dir.parts) > 8:
            excluded(
                "scan-depth-limit",
                current,
                "Manifest scan stops after 8 directories; configure a shallower project root.",
            )
            dirs[:] = []
            continue
        for name in sorted(files):
            path = current / name
            workflow = rel_dir.parts[:2] == (".github", "workflows")
            if not (adapters.is_manifest(name) or workflow):
                continue
            if path.is_symlink() or path.resolve() != path.absolute():
                excluded("manifest-symlink", path, "Symlinked manifest excluded.")
                continue
            try:
                size = path.stat().st_size
            except OSError:
                excluded("manifest-unreadable", path, "Manifest metadata unavailable.")
                continue
            if size > (LOCK_LIMIT if name in LOCK_NAMES else MANIFEST_LIMIT):
                excluded(
                    "manifest-too-large",
                    path,
                    "Manifest size limit exceeded; narrow the project root or split this manifest.",
                )
                continue
            count += 1
            if count > 2000:
                raise ValueError(
                    "manifest limit exceeded (2000); choose a narrower repository root or exclude generated manifests; no source scan performed"
                )
            yield path


def manifest_fingerprint(root: Path, profile: Profile | None = None) -> dict[str, str]:
    """Hash the bounded manifest inventory, including newly added/removed files.

    Always rediscover paths: reusing a previous profile would miss a new lockfile.
    The profile argument is accepted for callers already holding a profile.
    """
    root = Path(root).resolve()
    result = {}
    for path in manifest_paths(root):
        try:
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                remaining = (LOCK_LIMIT if path.name in LOCK_NAMES else MANIFEST_LIMIT) + 1
                while remaining:
                    chunk = handle.read(min(65536, remaining))
                    if not chunk:
                        break
                    digest.update(chunk)
                    remaining -= len(chunk)
            if remaining:
                result[path.relative_to(root).as_posix()] = digest.hexdigest()
        except OSError:
            continue
    return dict(sorted(result.items()))


def _xml_manifest(text):
    # No entity expansion or external definitions are needed in a build manifest.
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.I):
        raise ValueError("XML declarations are unsupported")
    tree = ET.fromstring(text)
    for element in tree.iter():
        element.tag = element.tag.rsplit("}", 1)[-1]
    return tree


def _property_value(value, properties):
    value = value or "detected"
    for _ in range(8):
        if len(value) > 100:
            return "unresolved"
        resolved = re.sub(
            r"\$\{([^}]+)\}|\$\(([^)]+)\)", lambda m: properties.get(m[1] or m[2], m[0]), value
        )
        if resolved == value:
            break
        value = resolved
    return "unresolved" if "$" in value else value


def _without_build_comments(text):
    """Remove comments without executing config or interpreting quoted strings."""
    pattern = r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|//[^\n]*|/\*[\s\S]*?\*/"""
    return re.sub(pattern, lambda m: " " if m[0].startswith(("//", "/*")) else m[0], text)


def profile_repo(root: Path, *, paths=None) -> Profile:
    root = Path(root).resolve()
    p = Profile()
    feature_slots: dict[str, set[str]] = {}
    component_keys = set()

    def add(name, version="detected", *, kind="declaration", ecosystem=None, role=None):
        package = name.lower()
        ecosystem = ecosystem or {
            "requirements.txt": "pypi",
            "pyproject.toml": "pypi",
            "go.mod": "go",
            "pom.xml": "maven",
            "build.gradle": "gradle",
            "build.gradle.kts": "gradle",
        }.get(path.name)
        if ecosystem == "pypi":
            # PyPI distribution names ignore case and runs of '.', '_' and '-'.
            package = re.sub(r"[-_.]+", "-", package)
        engine = DATABASE_CLIENTS.get(package) if role != "server" and kind != "inference" else None
        name = ALIASES.get(package, package)
        if engine:
            role = "client"
            if name == engine:
                name += "-client"
        # Git/URL dependency specs may contain credentials; retain only the fact of detection.
        version = str(version)
        if not re.fullmatch(r"[a-zA-Z0-9^~<>=!.*+|, /_-]{1,100}", version):
            version = "unresolved"
        if version == "detected" and kind == "declaration":
            kind = "detection"
        source = {"path": relative, "version": version, "kind": kind}
        if role:
            source.update(role=role, package=package)
        if ecosystem:
            source["ecosystem"] = ecosystem
            constraint = version
            if (
                ecosystem == "cargo"
                and kind == "declaration"
                and re.fullmatch(
                    r"\d+(?:\.\d+){0,2}(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", version
                )
            ):
                constraint = "^" + version
            elif ecosystem == "julia" and kind == "declaration":
                constraint = adapters.julia_constraint(version)
            source["constraint"] = constraint
        component = {
            "name": package,
            "technology": name,
            "role": role or "dependency",
            "source": relative,
            "version": version,
            "kind": kind,
        }
        if ecosystem:
            component["ecosystem"] = ecosystem
        if engine:
            component["engine"] = engine
        component_key = tuple(sorted(component.items()))
        if component_key not in component_keys:
            component_keys.add(component_key)
            p.components.append(component)
        sources = p.technology_sources.setdefault(name, [])
        if source not in sources:
            sources.append(source)
        if kind in {"lock", "runtime"} and version not in {"detected", "unresolved"}:
            resolved = p.resolved_versions.setdefault(name, [])
            if version not in resolved:
                resolved.append(version)
                resolved.sort()
        # A resolved transitive package is evidence about the lock, not a direct
        # repository technology. Retain its provenance without creating skills.
        if kind == "lock":
            return
        if engine:
            add(engine, kind="inference", role="server")
        # Hints and concrete lock resolutions must not turn a declared range into
        # 'multiple'. Keep every source so monorepo declarations remain inspectable.
        for source_kind in ("declaration", "runtime"):
            versions = sorted(
                {
                    s["version"]
                    for s in sources
                    if s["kind"] == source_kind and s["version"] not in {"detected", "unresolved"}
                }
            )
            if versions:
                p.technologies[name] = versions[0] if len(versions) == 1 else "multiple"
                break
        else:
            p.technologies[name] = "unresolved" if version == "unresolved" else "detected"
        if name in {"tauri-api", "tauri-cli"}:
            add("tauri", kind="detection")
        if name == "hardhat":
            add("solidity", kind="inference")

    def jvm_dependency(group, artifact, version, ecosystem):
        if not group or not artifact:
            return
        add(f"{group}:{artifact}", version, ecosystem=ecosystem)
        if group == "org.springframework.boot" and artifact.startswith("spring-boot"):
            add("spring", version, ecosystem=ecosystem)
        elif group == "org.springframework" and artifact.startswith("spring-"):
            add("spring", version, ecosystem=ecosystem)

    def python_dependency(spec):
        # Read declarations without evaluating environment markers or importing
        # packages. Hardware requirements remain useful target evidence on CI.
        match = re.match(r"\s*([\w.-]+)(?:\[[^]]+\])?\s*([^;#]*)", spec)
        if match:
            add(match[1], match[2].strip() or "detected", ecosystem="pypi")

    def maven_manifest(text):
        tree = _xml_manifest(text)
        properties = {
            element.tag: (element.text or "").strip() for element in tree.findall("./properties/*")
        }
        for key in ("java.version", "maven.compiler.release", "maven.compiler.target"):
            if key in properties:
                add("java", _property_value(properties[key], properties), ecosystem="maven")
                break
        for dependency in tree.findall(".//dependency") + tree.findall("./parent"):
            group = dependency.findtext("groupId", "").strip()
            artifact = dependency.findtext("artifactId", "").strip()
            version = _property_value(dependency.findtext("version"), properties)
            jvm_dependency(group, artifact, version, "maven")

    def gradle_manifest(text):
        text = _without_build_comments(text)
        for version in re.findall(
            r"""\bid\s*(?:\(\s*)?["']org\.springframework\.boot["']\s*\)?\s*version\s*["']([^"']+)["']""",
            text,
        ):
            add("spring", version, ecosystem="gradle")
        for group, artifact, version in re.findall(
            r"""\b(?:implementation|api|compileOnly|runtimeOnly|testImplementation|classpath)\s*(?:\(\s*)?["']([\w.-]+):([\w.-]+):([^"']+)["']""",
            text,
        ):
            jvm_dependency(group, artifact, "unresolved" if "$" in version else version, "gradle")
        java = re.search(r"JavaLanguageVersion\.of\(\s*(\d+)\s*\)", text)
        if not java:
            java = re.search(
                r"""\b(?:sourceCompatibility|targetCompatibility)\s*=\s*(?:JavaVersion\.VERSION_)?["']?(\d+(?:\.\d+)?)""",
                text,
            )
        if java:
            add("java", java[1], ecosystem="gradle")

    def dotnet_manifest(text):
        tree = _xml_manifest(text)
        properties = {
            element.tag: (element.text or "").strip()
            for element in tree.findall("./PropertyGroup/*")
        }
        sdk = tree.get("Sdk", "").lower()
        web = "microsoft.net.sdk.web" in sdk or any(
            element.get("Name", "").lower() == "microsoft.net.sdk.web"
            for element in tree.findall("./Sdk")
        )
        if web:
            add("aspnet", ecosystem="nuget")
        for framework in (
            properties.get("TargetFramework") or properties.get("TargetFrameworks", "")
        ).split(";"):
            target = re.fullmatch(r"net(\d+\.\d+)(?:-[\w.-]+)?", framework.strip())
            if target:
                add("dotnet", target[1], ecosystem="nuget")
                if web:
                    add("aspnet", target[1], ecosystem="nuget")
        if properties.get("RuntimeFrameworkVersion"):
            add(
                "dotnet",
                _property_value(properties["RuntimeFrameworkVersion"], properties),
                kind="runtime",
                ecosystem="nuget",
            )
        for reference in tree.findall(".//PackageReference"):
            package = reference.get("Include", reference.get("Update", ""))
            if not package:
                continue
            version = _property_value(
                reference.get("Version") or reference.findtext("Version"), properties
            )
            add(package, version, ecosystem="nuget")
            if package.lower().startswith("microsoft.entityframeworkcore"):
                add("entityframework", version, ecosystem="nuget")
            if package.lower().startswith("microsoft.aspnetcore"):
                add("aspnet", version, ecosystem="nuget")
        for reference in tree.findall(".//FrameworkReference"):
            if reference.get("Include", "").lower() == "microsoft.aspnetcore.app":
                add("aspnet", ecosystem="nuget")

    def hardhat_manifest(text):
        text = _without_build_comments(text)
        match = re.search(r"""\bsolidity\s*:\s*(?:["'](\d+\.\d+\.\d+)["']|\{)""", text)
        versions = []
        if match and match[1]:
            versions.append(match[1])
        elif match:
            # Bound version keys to the solidity object; unrelated plugin versions
            # and contract source pragmas do not describe the selected compiler.
            depth, end = 1, match.end()
            tokens = re.finditer(r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[{}]""", text[end:])
            for token in tokens:
                if token[0] == "{":
                    depth += 1
                elif token[0] == "}":
                    depth -= 1
                    if depth == 0:
                        end += token.start()
                        break
            else:
                return
            versions.extend(
                re.findall(r"""\bversion\s*:\s*["'](\d+\.\d+\.\d+)["']""", text[match.end() : end])
            )
        add("hardhat", kind="detection")
        for version in versions:
            add("solidity", version)
            add("solc", version, kind="runtime")

    for path in manifest_paths(root, diagnostics=p.diagnostics) if paths is None else paths:
        relative = path.relative_to(root).as_posix()
        p.manifests.append(relative)
        try:
            limit = LOCK_LIMIT if path.name in LOCK_NAMES else MANIFEST_LIMIT
            with path.open("rb") as handle:
                raw = handle.read(limit + 1)
            if len(raw) > limit:
                p.warnings.append(f"{relative}: size limit exceeded")
                continue
            text = raw.decode("utf-8-sig")
            name = path.name
            adapter = adapters.adapter_for(name)
            if adapter is not None and adapter.extract is not None:
                for observation in adapter.extract(text):
                    add(**asdict(observation))
            if name in {"package-lock.json", "npm-shrinkwrap.json"}:
                data = json.loads(text)
                for location, spec in data.get("packages", {}).items():
                    if "node_modules/" in location and isinstance(spec, dict):
                        dep = spec.get("name") or location.rsplit("node_modules/", 1)[-1]
                        add(dep, spec.get("version", "unresolved"), kind="lock", ecosystem="npm")
                pending = list(data.get("dependencies", {}).items())
                while pending:
                    dep, spec = pending.pop()
                    if isinstance(spec, dict):
                        add(dep, spec.get("version", "unresolved"), kind="lock", ecosystem="npm")
                        pending.extend(spec.get("dependencies", {}).items())
            elif name == "Cargo.lock":
                for package in tomllib.loads(text).get("package", []):
                    add(package["name"], package.get("version", "unresolved"), kind="lock")
            elif name in {"rust-toolchain.toml", "rust-toolchain"}:
                channel = (
                    tomllib.loads(text).get("toolchain", {}).get("channel", "detected")
                    if name.endswith(".toml")
                    else text.strip()
                )
                add("rust", channel, kind="runtime")
            elif name in {".nvmrc", ".python-version"}:
                add("node" if name == ".nvmrc" else "python", text.strip(), kind="runtime")
            elif name in {"tauri.conf.json", "tauri.conf.json5", "Tauri.toml"}:
                add("tauri")
            elif name == "package.json":
                data = json.loads(text)
                add("javascript")
                if data.get("engines", {}).get("node"):
                    add("node", data["engines"]["node"])
                package_manager = re.fullmatch(
                    r"(npm|pnpm|yarn|bun)@(\d+\.\d+\.\d+)(?:\+.*)?",
                    str(data.get("packageManager", "")),
                )
                if package_manager:
                    add(package_manager[1], package_manager[2], kind="runtime")
                for section in (
                    "dependencies",
                    "devDependencies",
                    "peerDependencies",
                    "optionalDependencies",
                ):
                    for dep, version in data.get(section, {}).items():
                        add(dep, version, ecosystem="npm")
                # Store script names, not arbitrary commands/secrets from scripts.
                p.commands[relative] = {
                    key: "npm run " + key
                    for key in data.get("scripts", {})
                    if key in {"test", "lint", "build", "typecheck", "test:e2e"}
                }
            elif name == "pyproject.toml":
                data = tomllib.loads(text)
                project = data.get("project", {})
                add("python", project.get("requires-python", "detected"))
                deps = list(project.get("dependencies", []))
                for group in project.get("optional-dependencies", {}).values():
                    deps.extend(group)
                for group in data.get("dependency-groups", {}).values():
                    deps.extend(x for x in group if isinstance(x, str))
                poetry = data.get("tool", {}).get("poetry", {})
                for dep, version in poetry.get("dependencies", {}).items():
                    add(
                        dep,
                        version
                        if isinstance(version, str)
                        else version.get("version", "unresolved"),
                    )
                for dep in deps:
                    python_dependency(dep)
                for tool in data.get("tool", {}):
                    if tool in {"ruff", "pytest", "mypy", "uv", "poetry", "hatch"}:
                        add(tool)
            elif name == "Cargo.toml":
                data = tomllib.loads(text)
                add("rust", data.get("package", {}).get("rust-version", "detected"))
                # Exact metadata tags describe domains without scanning source code.
                for keyword in data.get("package", {}).get("keywords", []):
                    if keyword in {"rtp-midi", "osc", "midi"}:
                        add("midir" if keyword == "midi" else keyword, kind="metadata")
                sections = [data, data.get("workspace", {})]
                sections.extend(data.get("target", {}).values())
                for section in sections:
                    for key in ("dependencies", "dev-dependencies", "build-dependencies"):
                        for dep, version in section.get(key, {}).items():
                            spec = version if isinstance(version, dict) else {}
                            dep = spec.get("package", dep)
                            add(
                                dep,
                                version
                                if isinstance(version, str)
                                else version.get("version", "unresolved"),
                                ecosystem="cargo",
                            )
                            features = spec.get("features", [])
                            if dep == "cpal" and "asio" in features:
                                add("asio", kind="feature")
                            if dep == "tokio" and "process" in features:
                                feature_slots.setdefault("process-workers", set()).add(dep)
                            if (
                                dep in {"windows", "windows-sys"}
                                and "Win32_System_JobObjects" in features
                            ):
                                feature_slots.setdefault("process-workers", set()).add(dep)
            elif name == "go.mod":
                add("go", next(iter(re.findall(r"(?m)^go\s+(\S+)", text)), "detected"))
                for dep, version in re.findall(
                    r"(?m)^\s*(?:require\s+)?([\w./-]+)\s+(v[\w.+-]+)", text
                ):
                    add(dep, version)
            elif name == "requirements.txt":
                add("python")
                for line in text.splitlines():
                    if line.lstrip().startswith(("#", "-")):
                        continue
                    python_dependency(line)
            elif name == "composer.json":
                add("php")
                for dep, version in json.loads(text).get("require", {}).items():
                    add("laravel" if dep == "laravel/framework" else dep, version)
            elif name == "Gemfile":
                add("ruby")
                if re.search(r"gem\s+['\"]rails['\"]", text):
                    add("rails")
            elif name == "components.json":
                add("shadcn")
            elif name.startswith("Dockerfile") or name in {
                "compose.yml",
                "compose.yaml",
                "docker-compose.yml",
                "docker-compose.yaml",
            }:
                add("docker")
                for image_spec in re.findall(
                    r"""(?:FROM\s+(?:--platform=\S+\s+)?|image:\s*)["']?([\w./:@-]+)""", text, re.I
                ):
                    image_spec = image_spec.split("@", 1)[0]
                    image, separator, version = image_spec.partition(":")
                    if not separator:
                        version = "detected"
                    image = image.removeprefix("docker.io/").removeprefix("library/")
                    if image in {
                        "postgres",
                        "mysql",
                        "redis",
                        "mongo",
                        "node",
                        "python",
                        "golang",
                        "rust",
                    }:
                        technology = {"mongo": "mongodb", "golang": "go"}.get(image, image)
                        add(technology, version, kind="runtime", ecosystem="docker", role="server")
                    elif image == "mcr.microsoft.com/mssql/server":
                        add("sqlserver", version, kind="runtime", ecosystem="docker", role="server")
            elif name.endswith(".tf"):
                add("terraform")
            elif name.endswith(".csproj"):
                add("dotnet")
                dotnet_manifest(text)
            elif name == "global.json":
                add("dotnet")
                sdk_version = json.loads(text).get("sdk", {}).get("version")
                if sdk_version:
                    add("dotnet-sdk", sdk_version, kind="runtime")
            elif name in {"pom.xml", "build.gradle", "build.gradle.kts"}:
                add("java")
                add("maven" if name == "pom.xml" else "gradle")
                if name == "pom.xml":
                    maven_manifest(text)
                else:
                    gradle_manifest(text)
            elif name in {"maven-wrapper.properties", "gradle-wrapper.properties"}:
                tool = "maven" if name.startswith("maven") else "gradle"
                distribution = re.search(r"(?m)^\s*distributionUrl\s*=\s*(\S+)", text)
                if distribution:
                    version = re.search(
                        r"(?:apache-maven-|gradle-)(\d+(?:\.\d+){1,3})-(?:bin|all)\.zip(?:[?#].*)?$",
                        distribution[1],
                    )
                    if version:
                        add(tool, version[1], kind="runtime")
            elif name == "foundry.toml":
                data = tomllib.loads(text)
                add("foundry")
                add("solidity")
                for settings in data.get("profile", {}).values():
                    if not isinstance(settings, dict):
                        continue
                    version = settings.get("solc_version", settings.get("solc"))
                    if isinstance(version, str) and re.fullmatch(r"\d+\.\d+\.\d+", version):
                        add("solidity", version)
                        add("solc", version, kind="runtime")
            elif name.startswith("hardhat.config."):
                hardhat_manifest(text)
            elif relative.startswith(".github/workflows/") or name == ".gitlab-ci.yml":
                add("github-actions" if relative.startswith(".github") else "gitlab-ci")
            for tool in (
                "typescript",
                "vitest",
                "jest",
                "playwright",
                "eslint",
                "webpack",
                "vite",
                "ruff",
                "pytest",
            ):
                if path.name.startswith(tool + ".") or (
                    tool == "typescript" and name.startswith("tsconfig")
                ):
                    add(tool)
        except (ValueError, TypeError, AttributeError, OSError, KeyError, ET.ParseError) as exc:
            p.warnings.append(f"{relative}: {type(exc).__name__}")
            p.diagnostics.append(
                {"code": "manifest-parse-error", "path": relative, "message": type(exc).__name__}
            )

    def slot(name, tech):
        p.slots.append(name)
        p.slot_technologies.setdefault(name, []).append(tech)

    for tech in sorted(p.technologies):
        if tech in adapters.LANGUAGES:
            slot("language-" + tech, tech)
        if tech in TECH_SLOTS:
            slot(TECH_SLOTS[tech], tech)
        if tech in adapters.TECH_SLOTS:
            slot(adapters.TECH_SLOTS[tech], tech)
        for domain in DOMAIN_SLOTS.get(tech, ()):
            slot(domain, tech)
        if any(
            source.get("ecosystem") == "pypi" and source.get("kind") != "lock"
            for source in p.technology_sources.get(tech, [])
        ):
            for domain in PYTHON_DOMAIN_SLOTS.get(tech, ()):
                slot(domain, tech)
    for feature_slot, technologies in sorted(feature_slots.items()):
        for tech in sorted(technologies):
            slot(feature_slot, tech)
    if {"playwright", "cypress", "selenium"} & p.technologies.keys():
        for tech in sorted({"playwright", "cypress", "selenium"} & p.technologies.keys()):
            slot("e2e-testing", tech)
    if {"eslint", "ruff", "mypy", "typescript"} & p.technologies.keys():
        for tech in sorted({"eslint", "ruff", "mypy", "typescript"} & p.technologies.keys()):
            slot("static-analysis", tech)
    languages = set(adapters.LANGUAGES)
    general_inputs = {
        "unit-testing": languages | {"vitest", "jest", "pytest", "testing-library", "unittest"},
        "build": languages
        | {
            "node",
            "cmake",
            "meson",
            "conan",
            "mix",
            "renv",
            "swift-tools",
            "flutter",
            "vite",
            "webpack",
            "npm",
            "pnpm",
            "yarn",
            "bun",
            "uv",
            "poetry",
            "hatch",
            "tauri",
            "tauri-api",
            "tauri-cli",
            "docker",
        },
        "ci-cd": languages | {"node", "github-actions", "gitlab-ci", "docker", "terraform"},
    }
    for general, inputs in general_inputs.items():
        p.slot_technologies[general] = sorted(inputs & p.technologies.keys())
    for general in ("architecture", "security", "performance", "refactoring", "documentation"):
        p.slot_technologies[general] = sorted(p.technologies)
    p.available_tools = [
        tool
        for tool in (
            "rtk",
            "git",
            "node",
            "npm",
            "pnpm",
            "yarn",
            "bun",
            "python",
            "uv",
            "trailmark",
            "cargo",
            "rustc",
            "go",
            "docker",
            "ruff",
            "pytest",
            "gh",
            "cmake",
            "ninja",
            "clang",
            "powershell",
            "pwsh",
            "bash",
        )
        if shutil.which(tool)
    ]
    p.slots = list(dict.fromkeys(p.slots))
    return p
