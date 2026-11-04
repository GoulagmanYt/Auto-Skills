#!/usr/bin/env python3
"""Bounded repo map; Python symbols use the standard-library AST, other files use paths."""

import argparse
import ast
import fnmatch
import os
from pathlib import Path

EXCLUDE = {
    ".git",
    ".codex",
    ".agents",
    "node_modules",
    "vendor",
    ".venv",
    "venv",
    "target",
    "dist",
    "build",
    "coverage",
    ".next",
    "__pycache__",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default=".")
    parser.add_argument("--limit", type=int, default=150)
    parser.add_argument("--symbols", action="store_true", help="parse Python AST symbols")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    target = (Path.cwd() / args.path).resolve()
    if not target.is_relative_to(root):
        parser.error("path must stay inside the repository")
    patterns = []
    ignore = root / ".codexignore"
    if ignore.is_file():
        patterns = [
            line.strip().rstrip("/")
            for line in ignore.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]

    def ignored(path):
        rel = path.relative_to(root).as_posix()
        return any(part in EXCLUDE for part in path.relative_to(root).parts) or any(
            fnmatch.fnmatch(rel, pat)
            or fnmatch.fnmatch(path.name, pat)
            or rel.startswith(pat.rstrip("/") + "/")
            for pat in patterns
        )

    printed, limit = 0, max(1, min(args.limit, 1000))
    for directory, dirs, files in os.walk(target, followlinks=False):
        dirs[:] = sorted(
            d
            for d in dirs
            if not ignored(Path(directory) / d) and not (Path(directory) / d).is_symlink()
        )
        for name in sorted(files):
            path = Path(directory) / name
            if path.is_symlink() or ignored(path):
                continue
            if printed >= limit:
                print(f"[map limited to {limit} files; narrow the path to continue]")
                return 0
            rel = path.relative_to(root).as_posix()
            print(rel)
            printed += 1
            if args.symbols and path.suffix == ".py" and path.stat().st_size < 200_000:
                try:
                    tree = ast.parse(path.read_bytes(), filename=rel)
                    symbols = [
                        node
                        for node in ast.walk(tree)
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    ]
                    for node in sorted(symbols, key=lambda n: n.lineno)[:20]:
                        print(f"  {node.lineno}:{node.name}")
                except (SyntaxError, ValueError, OSError):
                    print("  [AST unavailable]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
