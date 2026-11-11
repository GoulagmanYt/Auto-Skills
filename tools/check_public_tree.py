"""Check the source file set intended for GitHub without printing sensitive values."""

import argparse
import subprocess
from pathlib import Path

from tools.check_artifacts import PUBLIC_DOCS, ROOT_FILES, SENSITIVE

LOCAL_PARTS = {
    ".git",
    ".serena",
    ".codex",
    ".agents",
    ".venv",
    "__pycache__",
    ".ruff_cache",
    "dist",
    "dist-alpha",
    "dist-ci",
    "dist-coverage",
    "build",
    "node_modules",
    ".benchmark-work",
}
PRIVATE_PREFIXES = (
    ("reports", "private"),
    ("reports", "benchmarks", "raw"),
    ("reports", "benchmarks", "recovery-measured"),
    ("docs", "superpowers"),
    (".superpowers",),
)


def is_private(relative):
    """Apply the same policy to indexed files and unstaged source exports."""
    parts = tuple(part.casefold() for part in relative.parts)
    return (
        any(part in LOCAL_PARTS for part in parts)
        or any(parts[: len(prefix)] == prefix for prefix in PRIVATE_PREFIXES)
        or any(part.startswith(".env") and part != ".env.example" for part in parts)
        or (
            parts[0] == "reports"
            and len(parts) > 1
            and parts[1].startswith(("ci-", "simulations", "user-projects"))
        )
    )


def source_paths(root):
    if (root / ".git").exists():
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=True
        )
        paths = [root / p.decode("utf-8") for p in result.stdout.split(b"\0") if p]
        if not paths:
            raise ValueError(
                "Git index is empty; stage the intended source before checking publication"
            )
        return paths

    def allowed(path):
        parts = path.relative_to(root).parts
        if is_private(path.relative_to(root)):
            return False
        if len(parts) == 1:
            return path.name in ROOT_FILES | {".gitignore", ".gitattributes"}
        if parts[0] == "docs":
            return path.name in PUBLIC_DOCS
        return parts[0] in {
            "src",
            "tests",
            "tools",
            ".github",
            "reports",
            "examples",
            "fixtures",
            "benchmarks",
        } and path.suffix in {
            ".py",
            ".md",
            ".json",
            ".toml",
            ".txt",
            ".rs",
            ".js",
            ".mjs",
            ".yml",
            ".yaml",
        }

    return [p for p in root.rglob("*") if p.is_file() and allowed(p)]


def check_source(root):
    issues = []
    paths = source_paths(root)
    for path in paths:
        relative = path.relative_to(root)
        if is_private(relative):
            issues.append(f"{relative.as_posix()}: local/generated file")
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            issues.append(f"{relative.as_posix()}: redirected source")
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            issues.append(f"{relative.as_posix()}: unreadable/non-text file")
            continue
        for label, pattern in SENSITIVE:
            if pattern.search(text):
                issues.append(f"{relative.as_posix()}: {label}")
    if issues:
        raise ValueError("\n".join(issues))
    return len(paths)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        print(
            f"Public source check: {check_source(args.root.resolve())} text files; no flagged local state, personal paths or credential values."
        )
    except ValueError as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
