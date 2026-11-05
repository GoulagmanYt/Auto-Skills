"""Fail closed on private files, unsafe members and leaked secrets in distributions."""

import argparse
import glob
import re
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT_FILES = {
    "README.md",
    "README.fr.md",
    "LICENSE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "CODE_OF_CONDUCT.md",
    "pyproject.toml",
    "MANIFEST.in",
    "install.sh",
    "install.ps1",
    "codex-auto-bootstrap",
    "codex-auto-bootstrap.ps1",
    "PKG-INFO",
    "setup.cfg",
}
PUBLIC_DOCS = {
    "configuration.md",
    "coverage.md",
    "positioning.md",
    "compatibility.md",
    "usage.md",
    "benchmark.md",
    "release.md",
    "public-alpha.md",
    "security-model.md",
}
REQUIRED_MODULES = {
    "adapters.py",
    "repo_config.py",
    "repo_inspection.py",
    "__init__.py",
    "__main__.py",
    "bootstrap.py",
    "catalog.py",
    "cli.py",
    "config.py",
    "context_preview.py",
    "discovery.py",
    "fs.py",
    "github.py",
    "installer.py",
    "lifecycle.py",
    "map_runtime.py",
    "policy.py",
    "profile.py",
    "proposal.py",
    "repository_uninstall.py",
    "selection.py",
    "token_runtime.py",
    "token_tools.py",
    "transaction.py",
    "workspaces.py",
}
PRIVATE_PARTS = {"__pycache__", ".serena", ".git", ".venv", "reports", "node_modules"}
# Values only: documentation may legitimately name an environment variable.
SENSITIVE = [
    ("personal Windows path", re.compile(r"[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s\"'<>]+", re.I)),
    ("personal Unix path", re.compile(r"/(?:Users|home)/[A-Za-z0-9_.-]+/")),
    ("OpenAI credential", re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}")),
    (
        "GitHub credential",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})"),
    ),
    ("AWS credential", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    (
        "credential assignment",
        re.compile(
            r"""(?i)(?:api[_-]?key|access[_-]?token|password|client[_-]?secret)["']?\s*[:=]\s*["'][A-Za-z0-9+/=_-]{24,}["']"""
        ),
    ),
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
]
MAX_MEMBER_BYTES = 8_000_000
MAX_ARCHIVE_BYTES = 64_000_000


def safe_name(name):
    path = PurePosixPath(name)
    if "\\" in name or path.is_absolute() or ".." in path.parts or ":" in name:
        raise ValueError("unsafe archive member name")
    if any(part in PRIVATE_PARTS for part in path.parts) or path.suffix in {".pyc", ".pyo"}:
        raise ValueError(f"private/generated member: {name}")
    return path


def allowed_sdist(path):
    parts = path.parts
    if len(parts) == 1:
        return path.name in ROOT_FILES
    if parts[0] == "src" and len(parts) == 3:
        return (parts[1] == "codex_bootstrap" and path.suffix == ".py") or (
            parts[1] == "codex_repo_auto_bootstrap.egg-info"
            and path.name
            in {
                "PKG-INFO",
                "SOURCES.txt",
                "dependency_links.txt",
                "entry_points.txt",
                "top_level.txt",
            }
        )
    if parts[0] in {"tests", "tools"}:
        return len(parts) == 2 and path.suffix == ".py"
    if parts[0] == "docs":
        return len(parts) == 2 and path.name in PUBLIC_DOCS
    if parts[0] == "examples":
        return path.suffix in {".json", ".toml", ".py", ".js", ".mjs", ".rs", ".md", ".txt"}
    if parts[0] == "benchmarks":
        return len(parts) == 2 and path.suffix in {".json", ".md"}
    return False


def allowed_wheel(path):
    parts = path.parts
    if parts[0] == "codex_bootstrap":
        return len(parts) == 2 and path.suffix == ".py"
    if re.fullmatch(r"codex_repo_auto_bootstrap-[A-Za-z0-9_.+]+\.dist-info", parts[0]):
        return (
            len(parts) == 2
            and path.name
            in {
                "METADATA",
                "WHEEL",
                "entry_points.txt",
                "top_level.txt",
                "RECORD",
                "LICENSE",
            }
            or len(parts) == 3
            and parts[1:] == ("licenses", "LICENSE")
        )
    return False


def members(archive):
    if archive.name.endswith(".whl"):
        with zipfile.ZipFile(archive) as stream:
            for item in stream.infolist():
                safe_name(item.filename)
                if (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("archive contains a symbolic link")
                if item.is_dir():
                    continue
                if item.file_size > MAX_MEMBER_BYTES:
                    raise ValueError("archive member exceeds size budget")
                yield item.filename, stream.read(item)
    elif archive.name.endswith(".tar.gz"):
        with tarfile.open(archive, "r:gz") as stream:
            for item in stream:
                safe_name(item.name)
                if item.isdir():
                    continue
                if not item.isfile():
                    raise ValueError("archive contains a link or special member")
                if item.size > MAX_MEMBER_BYTES:
                    raise ValueError("archive member exceeds size budget")
                with stream.extractfile(item) as member:
                    yield item.name, member.read()
    else:
        raise ValueError("expected wheel or .tar.gz source distribution")


def check_archive(archive):
    archive = Path(archive)
    wheel = archive.name.endswith(".whl")
    names, total, roots = set(), 0, set()
    for name, data in members(archive):
        total += len(data)
        if total > MAX_ARCHIVE_BYTES:
            raise ValueError("archive exceeds uncompressed size budget")
        path = safe_name(name)
        if not wheel:
            roots.add(path.parts[0])
            if len(path.parts) < 2:
                raise ValueError("source distribution has no enclosing directory")
            path = PurePosixPath(*path.parts[1:])
        relative = path.as_posix()
        if relative in names:
            raise ValueError(f"duplicate archive member: {relative}")
        names.add(relative)
        if not (allowed_wheel(path) if wheel else allowed_sdist(path)):
            raise ValueError(f"member outside public allowlist: {relative}")
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"unexpected binary member: {relative}") from exc
        for label, pattern in SENSITIVE:
            if pattern.search(content):
                # Never print the credential/path value, even when validation fails.
                raise ValueError(f"{label} found in {relative}")
    if not wheel and len(roots) != 1:
        raise ValueError("source distribution must have one enclosing directory")
    prefix = "codex_bootstrap/" if wheel else "src/codex_bootstrap/"
    required = {prefix + name for name in REQUIRED_MODULES}
    if wheel:
        metadata = {PurePosixPath(name).parts[0] for name in names if ".dist-info/" in name}
        if len(metadata) != 1:
            raise ValueError("wheel must have one metadata directory")
        directory = metadata.pop()
        required |= {
            directory + "/" + name for name in ("METADATA", "WHEEL", "RECORD", "entry_points.txt")
        }
    else:
        required |= ROOT_FILES - {"setup.cfg"}
        required |= {"docs/" + name for name in PUBLIC_DOCS}
        required |= {"tools/check_artifacts.py", "tools/verify_native_install.py"}
    missing = required - names
    if missing:
        raise ValueError("required distribution files missing: " + ", ".join(sorted(missing)))
    return {"artifact": archive.name, "members": len(names), "uncompressed_bytes": total}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", nargs="+", type=Path)
    args = parser.parse_args(argv)
    try:
        import json

        paths = []
        for path in args.artifacts:
            matches = (
                [Path(value) for value in glob.glob(str(path))]
                if glob.has_magic(str(path))
                else [path]
            )
            if not matches:
                raise ValueError("artifact pattern matched no files")
            paths.extend(matches)
        print(json.dumps([check_archive(path) for path in paths], indent=2))
    except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
        parser.exit(1, f"artifact validation failed: {exc}\n")


if __name__ == "__main__":
    main()
