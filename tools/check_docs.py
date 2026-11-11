"""Check local Markdown file targets in source exports and built distributions."""

import argparse
import posixpath
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


def missing_links(relative, text, available):
    issues = []
    # Anchors and external evidence are intentionally not fetched by offline CI.
    text = re.sub(r"(?ms)^```.*?^```[^\n]*", "", text)
    for match in re.finditer(r"\]\((?:<([^>]+)>|([^\s)]+))(?:\s+[^)]*)?\)", text):
        target = match[1] or match[2]
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        destination = posixpath.normpath(
            posixpath.join(posixpath.dirname(relative), unquote(parsed.path))
        )
        if destination.startswith(("../", "/")) or destination not in available:
            issues.append(f"{relative}: missing target {target}")
    return issues


def check_docs(root):
    try:
        from tools.check_public_tree import source_paths
    except ModuleNotFoundError:
        from check_public_tree import source_paths

    paths = source_paths(root)
    available = {path.relative_to(root).as_posix() for path in paths}
    issues, count = [], 0
    for path in paths:
        if path.suffix == ".md":
            count += 1
            issues.extend(
                missing_links(
                    path.relative_to(root).as_posix(),
                    path.read_text(encoding="utf-8-sig"),
                    available,
                )
            )
    if issues:
        raise ValueError("\n".join(issues))
    return count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        print(f"Documentation links: {check_docs(args.root.resolve())} Markdown files checked.")
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
