"""Keep native launcher paths stable across Codex standalone upgrades."""

from pathlib import Path


def launcher_path(path, *, migrate_release=False):
    # Resolving a symlink/junction would pin the wrapper to today's release.
    launcher = Path(path).expanduser().absolute()
    if (
        migrate_release
        and launcher.parent.name == "bin"
        and launcher.parent.parent.parent.name == "releases"
        and launcher.parent.parent.parent.parent.name == "standalone"
    ):
        standalone = launcher.parent.parent.parent.parent
        current = standalone / "current" / "bin" / launcher.name
        if current.is_file():
            return current
    return launcher
