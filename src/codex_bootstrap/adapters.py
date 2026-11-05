"""Declarative manifest inventory and bounded, static ecosystem adapters.

Adapters inspect text supplied by the manifest reader. They never import project
modules, evaluate build files, invoke package managers, or read source files.
Literal declarations are evidence; computed expressions remain unresolved.
"""

import configparser
import json
import re
import tomllib
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Evidence:
    name: str
    version: str = "detected"
    kind: str = "declaration"
    ecosystem: str | None = None
    role: str | None = None


def _comments(text, marker="#"):
    """Strip line comments while preserving quoted literal values."""
    pattern = r""""(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|""" + re.escape(marker) + r"[^\n]*"
    return re.sub(pattern, lambda match: "" if match[0].startswith(marker) else match[0], text)


def _cmake_commands(text):
    """Identify command calls, skipping comments, quoted and bracket arguments."""
    token = re.compile(
        r"#\[(?P<comment_eq>=*)\[[\s\S]*?\](?P=comment_eq)\]|#[^\n]*"
        r"|\[(?P<bracket_eq>=*)\[[\s\S]*?\](?P=bracket_eq)\]"
        r'|"(?:\\.|[^"\\])*"'
        r"|(?P<command>[A-Za-z_][\w]*)\s*\(|(?P<paren>[()])"
    )
    tokens = iter(token.finditer(text))
    for match in tokens:
        if not match.group("command"):
            continue
        depth = 1
        for end in tokens:
            if end.group("command") or end.group("paren") == "(":
                depth += 1
            elif end.group("paren") == ")":
                depth -= 1
            if depth == 0:
                yield match.group("command").lower(), _comments(text[match.end() : end.start()])
                break


def _cmake(text):
    commands = list(_cmake_commands(text))
    result = [Evidence("cmake", role="tool")]
    for command, arguments in commands:
        if command == "cmake_minimum_required":
            minimum = re.match(
                r'\s*VERSION\s+(?:"(\d+(?:\.\d+){1,2})"|(\d+(?:\.\d+){1,2}))(?=\s|$)',
                arguments,
                re.I,
            )
            if minimum:
                result.append(
                    Evidence(
                        "cmake",
                        ">=" + next(value for value in minimum.groups() if value),
                        role="tool",
                    )
                )
    languages = set()
    for project in (arguments for command, arguments in commands if command == "project"):
        declaration = re.search(r"\bLANGUAGES\s+(.+)", project, re.I | re.S)
        values = declaration[1] if declaration else project
        languages.update(re.findall(r"\b(CXX|C)\b", values))
        if not declaration and not languages:
            languages.update({"C", "CXX"})  # CMake's default project languages.
    for raw, language in (("C", "c"), ("CXX", "cpp")):
        versions = []
        for command, arguments in commands:
            if command == "set":
                standard = re.match(
                    r"\s*CMAKE_" + raw + r'_STANDARD\s+(?:"(\d+)"|(\d+))(?=\s|$)', arguments, re.I
                )
                if standard:
                    versions.append(next(value for value in standard.groups() if value))
            elif command in {"target_compile_features", "add_compile_features"}:
                feature = re.search(
                    r'(?:^|\s)(?:"'
                    + ("cxx" if raw == "CXX" else "c")
                    + r'_std_(\d+)"|'
                    + ("cxx" if raw == "CXX" else "c")
                    + r"_std_(\d+))(?=\s|$)",
                    arguments,
                )
                if feature:
                    versions.append(next(value for value in feature.groups() if value))
        if raw in languages or versions:
            result.append(
                Evidence(
                    language,
                    versions[0] if versions else "detected",
                    role="language",
                )
            )
    return result


def _meson(text):
    text = _comments(text)
    result = [Evidence("meson", role="tool")]
    project = re.search(r"\bproject\s*\(([\s\S]*?)\)(?:\s|$)", text)
    if not project:
        return result
    body = project[1]
    minimum = re.search(r"meson_version\s*:\s*['\"]([^'\"]+)['\"]", body)
    if minimum:
        result.append(Evidence("meson", minimum[1], role="tool"))
    positional = body.split(":", 1)[0]
    for language in ("c", "cpp"):
        if re.search(r"['\"]" + language + r"['\"]", positional):
            standard = re.search(r"\b" + language + r"_std=(?:c\+\+|gnu\+\+|c|gnu)?(\d+)", body)
            result.append(
                Evidence(language, standard[1] if standard else "detected", role="language")
            )
    return result


def _conan(text):
    data = configparser.ConfigParser(interpolation=None, allow_no_value=True, strict=False)
    data.optionxform = str
    try:
        data.read_string(text)
    except configparser.Error:
        raise ValueError("invalid Conan manifest") from None
    result = [Evidence("conan", role="tool"), Evidence("cpp", role="language")]
    for item in data["requires"] if "requires" in data else ():
        package = re.fullmatch(r"([\w.+-]+)/([\w.+~-]+)(?:@[^\s]+)?", item)
        if package:
            result.append(Evidence(package[1], package[2], ecosystem="conan"))
    return result


def _pubspec(text):
    # A deliberately small YAML subset: indentation maps and literal scalars.
    # Tags, anchors, custom constructors and computed values are never evaluated.
    result = [Evidence("dart", role="language")]
    section = None
    dependency = None
    for line in _comments(text).splitlines():
        match = re.match(r"^( *)([A-Za-z_][\w-]*)\s*:\s*(.*?)\s*$", line)
        if not match:
            continue
        indent, key, value = len(match[1]), match[2], match[3].strip("\"'")
        if indent == 0:
            section, dependency = key, None
            continue
        if section == "environment" and indent == 2 and key in {"sdk", "flutter"}:
            if value and re.fullmatch(r"[\d^~<>=.*+|, -]+", value):
                result.append(
                    Evidence(
                        "dart" if key == "sdk" else "flutter",
                        value,
                        role="language" if key == "sdk" else "framework",
                    )
                )
        elif section in {"dependencies", "dev_dependencies", "dependency_overrides"}:
            if indent == 2:
                dependency = key
                result.append(
                    Evidence(
                        key,
                        value
                        if value and re.fullmatch(r"[\d^~<>=.*+|, -]+", value)
                        else "detected",
                        ecosystem="pub",
                    )
                )
            elif indent == 4 and dependency and key == "version":
                result.append(Evidence(dependency, value, ecosystem="pub"))
    return result


def _swift(text):
    header = re.search(r"(?m)^\s*//\s*swift-tools-version:\s*([\d.]+)", text)
    text = _comments(re.sub(r"/\*[\s\S]*?\*/", "", text), "//")
    result = [Evidence("swift", role="language")]
    if header:
        result.append(Evidence("swift-tools", header[1], role="tool"))
    modes = re.search(r"\bswiftLanguage(?:Versions|Modes)\s*:\s*\[([^]]+)\]", text)
    if modes:
        for version in re.findall(r"\.v(\d+)(?:_(\d+))?\b", modes[1]):
            result.append(
                Evidence("swift", ".".join(part for part in version if part), role="language")
            )
    return result


def _mix(text):
    text = _comments(text)
    result = [Evidence("elixir", role="language"), Evidence("mix", role="tool")]
    version = re.search(r"""\belixir:\s*["']([^"']+)["']""", text)
    if version:
        result.append(Evidence("elixir", version[1], role="language"))
    for package, version in re.findall(r"""\{\s*:([\w]+)\s*,\s*["']([^"']+)["']""", text):
        result.append(Evidence(package, version, ecosystem="hex"))
    return result


def _description(text):
    fields = {}
    field = None
    for line in text.splitlines():
        if line[:1].isspace() and field:
            fields[field] += " " + line.strip()
        elif ":" in line:
            field, value = line.split(":", 1)
            fields[field] = value.strip()
    result = [Evidence("r", role="language")]
    for field in ("Depends", "Imports", "Suggests", "LinkingTo"):
        for spec in fields.get(field, "").split(","):
            package = re.fullmatch(r"\s*([A-Za-z][\w.]*)\s*(?:\(([^)]+)\))?\s*", spec)
            if package:
                name = "r" if package[1] == "R" else package[1]
                result.append(
                    Evidence(
                        name,
                        package[2] or "detected",
                        ecosystem="cran",
                        role="language" if name == "r" else "dependency",
                    )
                )
    return result


def _renv(text):
    data = json.loads(text)
    result = [
        Evidence(
            "r", data.get("R", {}).get("Version", "detected"), kind="runtime", role="language"
        ),
        Evidence("renv", role="tool"),
    ]
    for name, package in data.get("Packages", {}).items():
        result.append(
            Evidence(name, package.get("Version", "unresolved"), kind="lock", ecosystem="cran")
        )
    return result


def _julia(text):
    data = tomllib.loads(text)
    compat = data.get("compat", {})
    result = [
        Evidence("julia", compat.get("julia", "detected"), ecosystem="julia", role="language")
    ]
    for section in ("deps", "weakdeps", "extras"):
        for package in data.get(section, {}):
            result.append(Evidence(package, compat.get(package, "detected"), ecosystem="julia"))
    return result


def julia_constraint(version):
    """Translate Julia's documented caret defaults and comma unions safely.

    https://pkgdocs.julialang.org/v1.10/compatibility/
    Unsupported forms stay unresolved instead of entering generic semver parsing.
    """
    result = []
    for alternative in version.split(","):
        alternative = alternative.strip()
        if re.fullmatch(r"\d+(?:\.\d+){0,2}", alternative):
            result.append("^" + alternative)
        elif re.fullmatch(r"[\^~]\s*\d+(?:\.\d+){0,2}", alternative):
            result.append(alternative)
        elif re.fullmatch(r"(?:>=|<)\s*\d+(?:\.\d+){0,2}|=\s*\d+\.\d+\.\d+", alternative):
            result.append(alternative)
        else:
            return "unresolved"
    return " || ".join(result)


@dataclass(frozen=True)
class Adapter:
    name: str
    filenames: frozenset[str]
    package_filenames: frozenset[str] = frozenset()
    extract: Callable[[str], list[Evidence]] | None = None
    suffixes: tuple[str, ...] = ()
    package_suffixes: tuple[str, ...] = ()
    pattern: str | None = None
    lockfiles: frozenset[str] = frozenset()

    def matches(self, name):
        return (
            name in self.filenames
            or name.endswith(self.suffixes)
            or bool(self.pattern and re.match(self.pattern, name))
        )

    def is_boundary(self, name):
        return name in self.package_filenames or name.endswith(self.package_suffixes)


# Legacy extractors remain in profile.py, with their inventory/ownership declared
# here. New ecosystems add a declaration and a pure text extractor in this module.
ADAPTERS = (
    Adapter(
        "javascript",
        frozenset(
            {
                "package.json",
                ".nvmrc",
                "package-lock.json",
                "npm-shrinkwrap.json",
                "pnpm-lock.yaml",
                "yarn.lock",
                "bun.lock",
            }
        ),
        frozenset({"package.json"}),
        lockfiles=frozenset(
            {"package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock"}
        ),
    ),
    Adapter(
        "python",
        frozenset(
            {
                "pyproject.toml",
                "requirements.txt",
                ".python-version",
                "uv.lock",
                "poetry.lock",
                "Pipfile.lock",
            }
        ),
        frozenset({"pyproject.toml", "requirements.txt"}),
        lockfiles=frozenset({"uv.lock", "poetry.lock", "Pipfile.lock"}),
    ),
    Adapter(
        "rust",
        frozenset(
            {
                "Cargo.toml",
                "Cargo.lock",
                "rust-toolchain.toml",
                "rust-toolchain",
                "tauri.conf.json",
                "tauri.conf.json5",
                "Tauri.toml",
            }
        ),
        frozenset({"Cargo.toml"}),
        lockfiles=frozenset({"Cargo.lock"}),
    ),
    Adapter(
        "go",
        frozenset({"go.mod", "go.sum"}),
        frozenset({"go.mod"}),
        lockfiles=frozenset({"go.sum"}),
    ),
    Adapter(
        "ruby",
        frozenset({"Gemfile", "Gemfile.lock"}),
        frozenset({"Gemfile"}),
        lockfiles=frozenset({"Gemfile.lock"}),
    ),
    Adapter(
        "php",
        frozenset({"composer.json", "composer.lock"}),
        frozenset({"composer.json"}),
        lockfiles=frozenset({"composer.lock"}),
    ),
    Adapter(
        "jvm",
        frozenset(
            {
                "pom.xml",
                "build.gradle",
                "build.gradle.kts",
                "gradle-wrapper.properties",
                "maven-wrapper.properties",
            }
        ),
        frozenset({"pom.xml", "build.gradle", "build.gradle.kts"}),
    ),
    Adapter(
        "dotnet", frozenset({"global.json"}), suffixes=(".csproj",), package_suffixes=(".csproj",)
    ),
    Adapter(
        "solidity",
        frozenset(
            {
                "foundry.toml",
                "hardhat.config.js",
                "hardhat.config.cjs",
                "hardhat.config.mjs",
                "hardhat.config.ts",
            }
        ),
        frozenset({"foundry.toml"}),
    ),
    Adapter("cmake", frozenset({"CMakeLists.txt"}), frozenset({"CMakeLists.txt"}), _cmake),
    Adapter("meson", frozenset({"meson.build"}), frozenset({"meson.build"}), _meson),
    Adapter("conan", frozenset({"conanfile.txt"}), frozenset({"conanfile.txt"}), _conan),
    Adapter("dart", frozenset({"pubspec.yaml"}), frozenset({"pubspec.yaml"}), _pubspec),
    Adapter("swift", frozenset({"Package.swift"}), frozenset({"Package.swift"}), _swift),
    Adapter("elixir", frozenset({"mix.exs"}), frozenset({"mix.exs"}), _mix),
    Adapter("r", frozenset({"DESCRIPTION"}), frozenset({"DESCRIPTION"}), _description),
    Adapter(
        "renv",
        frozenset({"renv.lock"}),
        frozenset({"renv.lock"}),
        _renv,
        lockfiles=frozenset({"renv.lock"}),
    ),
    Adapter("julia", frozenset({"Project.toml"}), frozenset({"Project.toml"}), _julia),
    Adapter(
        "configuration",
        frozenset(
            {
                "Dockerfile",
                "docker-compose.yml",
                "docker-compose.yaml",
                "compose.yaml",
                "compose.yml",
                ".gitlab-ci.yml",
                "Makefile",
                "justfile",
                "components.json",
                "auto-skills.toml",
            }
        ),
        suffixes=(".tf",),
        pattern=r"^(?:vite|vitest|playwright|jest|eslint|next|nuxt|svelte|tailwind|webpack|tsconfig|ruff|pytest|tox)\.(?:.*\.)?(?:json|[cm]?[jt]s|toml|ini)$",
    ),
)

LANGUAGES = frozenset(
    {
        "javascript",
        "typescript",
        "python",
        "rust",
        "go",
        "ruby",
        "php",
        "java",
        "dotnet",
        "solidity",
        "c",
        "cpp",
        "dart",
        "swift",
        "elixir",
        "r",
        "julia",
    }
)
TECH_SLOTS = {
    "cmake": "build-cmake",
    "meson": "build-meson",
    "conan": "build-conan",
    "flutter": "framework-flutter",
    "phoenix": "framework-phoenix",
    "renv": "build-renv",
    "mix": "build-mix",
}


def adapter_for(name):
    return next((adapter for adapter in ADAPTERS if adapter.matches(name)), None)


def is_manifest(name):
    return adapter_for(name) is not None


def is_package_manifest(name):
    return any(adapter.is_boundary(name) for adapter in ADAPTERS)


def lock_names():
    return set().union(*(adapter.lockfiles for adapter in ADAPTERS))
