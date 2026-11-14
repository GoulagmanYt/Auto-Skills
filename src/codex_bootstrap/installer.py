"""Owned, reversible user installation; the original Codex executable is untouched."""

import hashlib
import json
import os
import shlex
import shutil
import sys
import tempfile
import venv
from contextlib import contextmanager
from functools import wraps
from importlib.resources import files as package_files
from pathlib import Path

from .codex_paths import launcher_path
from .fs import atomic_write, command, confined, digest, json_text
from .repository_uninstall import remove_block, restore, snapshot
from .runtime_loader import installation_mutex, state_directory
from .transaction import decoded

BEGIN = "# >>> codex-auto-bootstrap >>>"
END = "# <<< codex-auto-bootstrap <<<"
BASE = ".local/share/codex-auto-bootstrap"


class WindowsRegistry:
    """The registry boundary is injectable so tests never touch HKCU."""

    def read_path(self):
        import winreg

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                return winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            return None

    def write_path(self, value, kind):
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            winreg.SetValueEx(key, "Path", 0, kind, value)

    def delete_path(self):
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, "Environment", 0, winreg.KEY_SET_VALUE
            ) as key:
                winreg.DeleteValue(key, "Path")
        except FileNotFoundError:
            pass

    def notify(self):
        import ctypes

        result = ctypes.c_size_t()
        ctypes.windll.user32.SendMessageTimeoutW(
            0xFFFF, 0x001A, 0, "Environment", 2, 1000, ctypes.byref(result)
        )


def shell_profiles(home, platform):
    if platform != "nt":
        return [home / name for name in (".profile", ".bashrc", ".zshrc", ".zprofile")]
    paths = set()
    for shell in filter(None, (shutil.which("powershell"), shutil.which("pwsh"))):
        value = command(
            [shell, "-NoProfile", "-NonInteractive", "-Command", "$PROFILE.CurrentUserAllHosts"]
        ).strip()
        if value:
            paths.add(Path(value))
    return sorted(paths)


def install_package(base, source):
    if not (source / "pyproject.toml").is_file():
        return Path(sys.executable)
    environment = base / "venv"
    if not (environment / "pyvenv.cfg").is_file():
        venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    command(
        [
            python,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-input",
            "--no-deps",
            "--upgrade",
            str(source),
        ],
        timeout=300,
        env=dict(os.environ, CODEX_BOOTSTRAP_DISABLE_RUNTIME="1"),
    )
    return python


def install_runtime_loader(base, python):
    """Install the stable entry selector only inside our own virtual environment."""
    if not python.is_relative_to(base) or not (base / "venv/pyvenv.cfg").is_file():
        return
    env = dict(os.environ, CODEX_BOOTSTRAP_DISABLE_RUNTIME="1")
    site = Path(
        command(
            [python, "-I", "-B", "-c", "import sysconfig;print(sysconfig.get_path('purelib'))"],
            timeout=15,
            env=env,
        ).strip()
    ).resolve()
    if not site.is_relative_to(base):
        raise ValueError("managed Python site-packages is outside installation")
    loader = site / "_codex_auto_bootstrap_runtime.py"
    atomic_write(
        loader, package_files("codex_bootstrap").joinpath("runtime_loader.py").read_bytes()
    )
    atomic_write(
        site / "codex_auto_bootstrap_runtime.pth",
        "import _codex_auto_bootstrap_runtime; _codex_auto_bootstrap_runtime.activate("
        + repr(str(base))
        + ")\n",
    )
    command(
        [
            python,
            "-I",
            "-B",
            "-c",
            "import py_compile,sys;py_compile.compile(sys.argv[1],doraise=True)",
            loader,
        ],
        timeout=15,
        env=env,
    )


def serialized_installation(function):
    @wraps(function)
    def protected(*args, **kwargs):
        home = Path(kwargs.get("home") or Path.home()).resolve()
        base = confined(home, BASE)
        with installation_mutex(base):
            if (state_directory(base) / "pending.json").exists():
                from .self_update import recover_pending

                recover_pending(base)
            return function(*args, **kwargs)

    return protected


def managed_block(path, content):
    old = path.read_bytes() if path.exists() else b""
    old = remove_block(old, BEGIN.encode(), END.encode())
    data = (
        old
        + (b"\n" if old else b"")
        + BEGIN.encode()
        + b"\n"
        + content.rstrip().encode()
        + b"\n"
        + END.encode()
        + b"\n"
    )
    mode = path.stat().st_mode & 0o7777 if path.exists() else 0o644
    restore(path, data, mode)
    return data


def _link_path(base, relative):
    """Confine a link's parent without following the link itself."""
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts or ":" in str(relative):
        raise ValueError("unsafe installation link path")
    return confined(base, relative.parent) / relative.name


def _canonical_owned_root(base):
    """Resolve explicit entry-point ancestors while preserving the owned root node."""
    base = Path(base).absolute()
    base = base.parent.resolve() / base.name
    if base.is_symlink() or (base.exists() and base.resolve() != base):
        raise ValueError("redirected installation root")
    return base


def _link_target(base, path, raw):
    requested_base = Path(base).absolute()
    base = _canonical_owned_root(requested_base)
    path = Path(path).absolute()
    if path.is_relative_to(requested_base):
        relative = path.relative_to(requested_base)
    elif path.is_relative_to(base):
        relative = path.relative_to(base)
    else:
        raise ValueError("installation link is outside the owned root")
    path = _link_path(base, relative)
    try:
        target = (path.parent / raw).resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("invalid or cyclic installation link") from exc
    venv_root = base / "venv"
    if (
        not path.is_relative_to(venv_root)
        or not target.is_relative_to(venv_root)
        or path.is_relative_to(target)
        or target == path
    ):
        raise ValueError("installation link must target a confined venv artifact")
    return target


def _scan_tree(base, *, validate_links=True, include_record=False):
    files, links, directories = {}, {}, {}
    base = _canonical_owned_root(base)
    if not base.exists():
        return files, links, directories
    pending = [base]
    while pending:
        directory = pending.pop()
        for path in directory.iterdir():
            relative = path.relative_to(base).as_posix()
            if path.is_symlink() or (path.exists() and path.resolve() != path):
                raw = os.readlink(path)
                if validate_links:
                    _link_target(base, path, raw)
                links[relative] = raw
            elif path.is_dir():
                directories[relative] = path.stat().st_mode & 0o7777
                pending.append(path)
            elif path.is_file():
                if include_record or path != base / "installation.json":
                    files[relative] = digest(path)
            else:
                raise ValueError("installation artifact is not a regular file or owned link")
    return files, links, directories


def _owned_files(base):
    return _scan_tree(base)[0]


def _validate_files(base, files, links=None):
    links = links or {}
    conflicts = []
    for relative, expected in files.items():
        if not relative.startswith(("bin/", "venv/")):
            raise ValueError(f"unowned installation artifact: {relative}")
        path = confined(base, relative)
        if path.exists() and (not path.is_file() or digest(path) != expected):
            conflicts.append(relative + ": modified artifact")
    for relative, expected in links.items():
        path = _link_path(base, relative)
        if not relative.startswith("venv/"):
            raise ValueError("unowned installation link")
        if path.is_symlink() or (path.exists() and path.resolve() != path):
            if os.readlink(path) != expected:
                conflicts.append(relative + ": modified link")
            else:
                _link_target(base, path, expected)
        elif path.exists():
            conflicts.append(relative + ": link replaced by a regular artifact")
    current_files, current_links, _ = _scan_tree(base)
    unknown = (set(current_files) - set(files)) | (set(current_links) - set(links))
    conflicts.extend(relative + ": unowned artifact" for relative in sorted(unknown))
    return conflicts


def _unlink_link(path):
    # Windows directory junctions need rmdir; symlinks are always unlinked.
    if path.is_symlink():
        path.unlink()
    else:
        path.rmdir()


def _restore_tree(base, backup, original, existed):
    if base.is_symlink() or (base.exists() and base.resolve() != base):
        _unlink_link(_link_path(base.parent, base.name))
    files, links, directories = _scan_tree(base, validate_links=False, include_record=True)
    for relative in links:
        _unlink_link(_link_path(base, relative))
    for relative in files:
        if relative not in original["files"]:
            confined(base, relative).unlink()
    for relative in sorted(directories, key=lambda s: len(Path(s).parts), reverse=True):
        if relative not in original["directories"]:
            confined(base, relative).rmdir()
    if existed:
        base.mkdir(parents=True, exist_ok=True)
    for relative, mode in original["directories"].items():
        path = confined(base, relative)
        path.mkdir(parents=True, exist_ok=True)
        os.chmod(path, mode)
    for relative, entry in original["files"].items():
        path = confined(base, relative)
        if not path.is_file() or digest(path) != entry["sha256"]:
            restore(path, confined(backup, "files/" + relative).read_bytes(), entry["mode"])
        elif path.stat().st_mode & 0o7777 != entry["mode"]:
            os.chmod(path, entry["mode"])
    for relative, raw in original["links"].items():
        path = _link_path(base, relative)
        target = _link_target(base, path, raw)
        path.symlink_to(raw, target_is_directory=target.is_dir())
    if not existed and base.exists():
        base.rmdir()


def _discard_recovery(backup):
    # The private backup contains only regular files and directories we created.
    _restore_tree(backup, backup, {"files": {}, "links": {}, "directories": {}}, False)


@contextmanager
def _installation_transaction(base, profiles, registry):
    existed = base.exists()
    files, links, directories = _scan_tree(base, include_record=True)
    base.parent.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix=".codex-bootstrap-recovery-", dir=base.parent))
    original = {"files": {}, "links": links, "directories": directories}
    live_profiles = {relative: snapshot(path) for relative, path in profiles.items()}
    registry_before = registry.read_path() if registry else None
    try:
        for relative, sha256 in files.items():
            source = confined(base, relative)
            mode = source.stat().st_mode & 0o7777
            destination = confined(backup, "files/" + relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            os.chmod(destination, 0o600)
            original["files"][relative] = {"sha256": sha256, "mode": mode}
        atomic_write(
            backup / "recovery.json",
            json_text(
                {
                    "base": str(base),
                    "existed": existed,
                    "original": original,
                    "profiles": live_profiles,
                    "registry": registry_before,
                }
            ),
        )
    except BaseException:
        _discard_recovery(backup)
        raise
    try:
        yield
    except BaseException as failure:
        try:
            _restore_tree(base, backup, original, existed)
            for relative, entry in live_profiles.items():
                if snapshot(profiles[relative]) != entry:
                    restore(profiles[relative], decoded(entry["before"]), entry["mode"])
            if registry and registry.read_path() != registry_before:
                if registry_before is None:
                    registry.delete_path()
                else:
                    registry.write_path(*registry_before)
        except BaseException as recovery_failure:
            raise RuntimeError(
                f"installation failed and automatic recovery could not finish; original snapshots retained at {backup}"
            ) from recovery_failure
        _discard_recovery(backup)
        raise failure
    else:
        _discard_recovery(backup)


@serialized_installation
def install(
    *,
    home=None,
    real=None,
    source=None,
    platform=None,
    profiles=None,
    registry=None,
    package_install=None,
    revision=None,
):
    """Install or update, retaining the first installation's exact original snapshots."""
    requested_home = Path(home or Path.home()).absolute()
    home = requested_home.resolve()
    platform = platform or os.name
    base = confined(home, BASE)
    record = confined(base, "installation.json")
    previous = json.loads(record.read_bytes()) if record.is_file() else None
    if previous is not None:
        if previous.get("version") != 2:
            raise ValueError(
                "legacy installation has no original snapshots; automatic update is unsafe"
            )
        conflicts = _validate_files(base, previous["files"], previous.get("links"))
        if conflicts:
            raise ValueError("; ".join(conflicts))
        if previous["platform"] != platform:
            raise ValueError("installation platform changed")
    elif base.exists() and any(base.iterdir()):
        raise ValueError("refusing to overwrite unowned installation directory")
    if real is None and previous:
        real = launcher_path(previous["real_codex"], migrate_release=True)
    real = real or shutil.which("codex")
    if real is None or not Path(real).is_file():
        raise ValueError("install Codex CLI before installing this wrapper")
    real = str(launcher_path(real))
    if Path(real).resolve().is_relative_to(base):
        raise ValueError("original Codex executable cannot be the wrapper")
    source = Path(source or Path(__file__).resolve().parents[2])
    source_project = (source / "pyproject.toml").is_file()
    if revision is None:
        from .self_update import source_revision

        revision = (
            source_revision(source) if source_project else (previous or {}).get("source_commit")
        )
    chosen_profiles = shell_profiles(home, platform) if profiles is None else profiles
    profile_paths = {}
    for candidate in chosen_profiles:
        absolute = Path(candidate).absolute()
        if absolute.is_relative_to(requested_home):
            relative = absolute.relative_to(requested_home).as_posix()
        elif absolute.is_relative_to(home):
            relative = absolute.relative_to(home).as_posix()
        else:
            raise ValueError("shell profile must be inside the selected home")
        profile_paths[relative] = confined(home, relative)
    entries = dict((previous or {}).get("profiles", {}))
    for relative, path in profile_paths.items():
        if relative not in entries:
            if path.exists() and BEGIN.encode() in path.read_bytes():
                raise ValueError("unowned managed profile block has no original snapshot")
            entries[relative] = snapshot(path)
        elif path.exists():
            unmanaged = remove_block(path.read_bytes(), BEGIN.encode(), END.encode())
            if unmanaged != (decoded(entries[relative]["before"]) or b""):
                entries[relative]["preserve_edits"] = True
    path_state = (previous or {}).get("path")
    registry = registry or (WindowsRegistry() if platform == "nt" else None)
    if platform == "nt" and path_state is None:
        original = registry.read_path()
        if original is not None and (not isinstance(original[0], str) or original[1] not in {1, 2}):
            raise ValueError("unsupported Windows PATH registry type")
        path_state = {
            "before": list(original) if original is not None else None,
            "inserted": False,
            "installed": None,
        }
    with _installation_transaction(base, profile_paths, registry):
        python = Path((package_install or install_package)(base, source)).resolve()
        install_runtime_loader(base, python)
        bin_dir = confined(base, "bin")
        for name in ("codex", "codex-auto-bootstrap"):
            if platform == "nt":
                atomic_write(
                    bin_dir / (name + ".cmd"),
                    '@echo off\r\n"'
                    + str(python)
                    + '" -B -m codex_bootstrap %*\r\nexit /b %errorlevel%\r\n',
                )
                atomic_write(
                    bin_dir / (name + ".ps1"),
                    "& '"
                    + str(python).replace("'", "''")
                    + "' -B -m codex_bootstrap @args\nexit $LASTEXITCODE\n",
                )
            else:
                atomic_write(
                    bin_dir / name,
                    "#!/bin/sh\nexec " + shlex.quote(str(python)) + ' -B -m codex_bootstrap "$@"\n',
                    executable=True,
                )
        function = (
            "function global:codex { & '"
            + str(python).replace("'", "''")
            + "' -B -m codex_bootstrap @args }\n"
            if platform == "nt"
            else "export PATH=" + shlex.quote(str(bin_dir)) + ':"$PATH"'
        )
        files, links, _ = _scan_tree(base)
        conflicts = _validate_files(base, files, links)
        if conflicts:
            raise ValueError("; ".join(conflicts))
        data = {
            "version": 2,
            "real_codex": real,
            "python": str(python),
            "bin": str(bin_dir),
            "platform": platform,
            "profiles": entries,
            "path": path_state,
            "files": files,
            "links": links,
            "source_commit": revision,
            "base_commit": revision
            if source_project or previous is None
            else previous.get("base_commit"),
            "runtime_path": None if source_project else (previous or {}).get("runtime_path"),
        }
        if previous and not source_project and "previous_commit" in previous:
            data.update(
                previous_commit=previous["previous_commit"],
                previous_runtime_path=previous.get("previous_runtime_path"),
            )
        atomic_write(record, json_text(data))
        for relative, path in profile_paths.items():
            installed = managed_block(path, function)
            entries[relative]["installed_sha256"] = hashlib.sha256(installed).hexdigest()
            atomic_write(record, json_text(data))
        if platform == "nt":
            current = registry.read_path()
            if (
                previous
                and (list(current) if current is not None else None) != path_state["installed"]
            ):
                path_state["preserve_edits"] = True
            old = current[0] if current else ""
            contains = any(part.casefold() == str(bin_dir).casefold() for part in old.split(";"))
            if not contains:
                updated = str(bin_dir) + (";" + old if old else "")
                path_state["inserted"] = True
                path_state["installed"] = [updated, 2]
                atomic_write(record, json_text(data))
                registry.write_path(updated, 2)
            elif path_state["installed"] is None:
                path_state["installed"] = list(current)
            registry.notify()
            atomic_write(record, json_text(data))
        return record


@serialized_installation
def uninstall(*, home=None, dry_run=False, platform=None, registry=None):
    home = Path(home or Path.home()).resolve()
    base = confined(home, BASE)
    record = confined(base, "installation.json")
    if not record.exists():
        return {"status": "not-installed", "conflicts": [], "actions": []}
    data = json.loads(record.read_bytes())
    if data.get("version") != 2:
        return {
            "status": "conflict",
            "conflicts": [
                "legacy installation has no ownership snapshots; preserve artifacts and PATH for manual review"
            ],
            "actions": [],
        }
    platform = platform or data["platform"]
    if platform != data["platform"]:
        raise ValueError("installation platform changed")
    conflicts = _validate_files(base, data["files"], data.get("links"))
    plans = {}
    for relative, entry in data["profiles"].items():
        path = confined(home, relative)
        if not path.exists():
            continue
        try:
            if not path.is_file():
                raise ValueError("not a regular file")
            now = path.read_bytes()
            if not entry.get("preserve_edits") and hashlib.sha256(now).hexdigest() == entry.get(
                "installed_sha256"
            ):
                plans[relative] = (decoded(entry["before"]), entry["mode"])
            else:
                cleaned = remove_block(now, BEGIN.encode(), END.encode())
                plans[relative] = (cleaned, path.stat().st_mode & 0o7777)
        except ValueError as exc:
            conflicts.append(relative + ": " + str(exc))
    registry = registry or (WindowsRegistry() if platform == "nt" else None)
    path_change = None
    path_state = data.get("path")
    if platform == "nt" and path_state and path_state["inserted"]:
        current = registry.read_path()
        if (
            current is not None
            and list(current) == path_state["installed"]
            and not path_state.get("preserve_edits")
        ):
            path_change = ("restore", path_state["before"])
        elif current is not None:
            if not isinstance(current[0], str) or current[1] not in {1, 2}:
                conflicts.append("Windows PATH has an unsupported registry type")
            else:
                bin_dir = str(confined(base, "bin"))
                parts = current[0].split(";")
                for index, part in enumerate(parts):
                    if part.casefold() == bin_dir.casefold():
                        del parts[index]
                        path_change = ("restore", [";".join(parts), current[1]])
                        break
    result = {
        "status": "conflict" if conflicts else ("dry-run" if dry_run else "uninstalled"),
        "conflicts": conflicts,
        "actions": sorted([*plans, *data["files"], *data.get("links", {})]),
    }
    if conflicts or dry_run:
        return result
    for relative, (content, mode) in plans.items():
        restore(confined(home, relative), content, mode)
    if path_change:
        value = path_change[1]
        if value is None:
            registry.delete_path()
        else:
            registry.write_path(*value)
        registry.notify()
    for relative in data["files"]:
        confined(base, relative).unlink(missing_ok=True)
    for relative in data.get("links", {}):
        path = _link_path(base, relative)
        if path.is_symlink() or path.exists():
            _unlink_link(path)
    record.unlink()
    for directory in sorted(
        [p for p in base.rglob("*") if p.is_dir()], key=lambda p: len(p.parts), reverse=True
    ):
        confined(base, directory.relative_to(base)).rmdir()
    base.rmdir()
    return result
