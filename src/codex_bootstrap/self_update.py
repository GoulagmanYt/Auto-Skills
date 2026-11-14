"""Bounded, background updates from the official GitHub main branch."""

import argparse
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from .fs import atomic_write, command, digest, json_text
from .runtime_loader import file_mutex, installation_mutex, state_directory

REPOSITORY = "GoulagmanYt/Auto-Skills"
REF_URL = f"https://api.github.com/repos/{REPOSITORY}/git/ref/heads/main"
INTERVAL = 86400
RETRY = 900


def installation_base(home=None):
    return Path(home or Path.home()).resolve() / ".local/share/codex-auto-bootstrap"


def read_json(path, limit=16_000_000):
    if path.is_symlink() or path.stat().st_size > limit:
        raise ValueError("invalid update metadata")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("invalid update metadata")
    return value


def _record(base):
    try:
        record = read_json(base / "installation.json")
        if record.get("version") != 2 or not isinstance(record.get("files"), dict):
            return None
        return record
    except (OSError, ValueError, RecursionError):
        return None


def _state(base):
    try:
        return read_json(state_directory(base) / "update.json", 64_000)
    except (OSError, ValueError, RecursionError):
        return {}


def _save_state(base, **values):
    directory = state_directory(base)
    with file_mutex(directory / "state.lock", timeout=5):
        state = _state(base)
        state.update(values)
        atomic_write(directory / "update.json", json_text(state))


def status(home=None):
    base = installation_base(home)
    record, state = _record(base), _state(base)
    enabled = state.get("enabled", bool(record and record.get("source_commit")))
    next_check = state.get("next_check", 0)
    if type(next_check) not in {int, float} or not math.isfinite(next_check):
        next_check = 0
    return {
        "installed": record is not None,
        "enabled": enabled is True,
        "repository": REPOSITORY,
        "branch": "main",
        "installed_commit": (record or {}).get("source_commit"),
        "runtime_path": (record or {}).get("runtime_path"),
        "last_result": state.get("last_result", "never-checked"),
        "next_check": next_check,
        "last_error": state.get("last_error"),
    }


def configure(home=None, *, enabled):
    _save_state(installation_base(home), enabled=bool(enabled), next_check=0)
    return status(home)


class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or parsed.hostname not in {
            "api.github.com",
            "codeload.github.com",
        }:
            raise ValueError("update redirect outside official GitHub hosts")
        return super().redirect_request(request, response, code, message, headers, newurl)


def fetch(url, limit):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Auto-Skills-self-update", "Accept": "application/vnd.github+json"},
    )
    with urllib.request.build_opener(OfficialRedirect()).open(request, timeout=10) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("update download exceeds budget")
    return data


def latest_commit(fetcher=None):
    value = json.loads((fetcher or fetch)(REF_URL, 256_000))
    object_value = value.get("object") if isinstance(value, dict) else None
    revision = object_value.get("sha") if isinstance(object_value, dict) else None
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("GitHub returned an invalid revision")
    return revision


def _relative(name):
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or ".." in path.parts or ":" in name or "\\" in name:
        raise ValueError("unsafe update archive path")
    return path


def extract_source(data, destination):
    destination.mkdir(parents=True, exist_ok=True)
    roots, total = set(), 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for index, member in enumerate(archive):
            if index >= 10000 or member.size < 0:
                raise ValueError("update archive exceeds budget")
            path = _relative(member.name)
            roots.add(path.parts[0])
            if len(roots) != 1 or (not member.isdir() and not member.isfile()):
                raise ValueError("unsupported update archive member")
            target = destination.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            total += member.size
            if total > 128_000_000:
                raise ValueError("update archive exceeds budget")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
    if len(roots) != 1:
        raise ValueError("empty update archive")
    root = destination / roots.pop()
    if (
        not (root / "pyproject.toml").is_file()
        or not (root / "src/codex_bootstrap/__init__.py").is_file()
    ):
        raise ValueError("archive is not the bootstrap project")
    return root


def source_revision(source):
    if not (source / ".git").exists():
        return None
    try:
        remote = (
            command(["git", "-C", source, "remote", "get-url", "origin"], timeout=5)
            .strip()
            .removesuffix(".git")
            .lower()
        )
        if remote not in {
            "https://github.com/" + REPOSITORY.lower(),
            "git@github.com:" + REPOSITORY.lower(),
        }:
            return None
        # A local feature commit must not silently revert to an older public main.
        command(
            [
                "git",
                "-C",
                source,
                "merge-base",
                "--is-ancestor",
                "HEAD",
                "refs/remotes/origin/main",
            ],
            timeout=5,
        )
        dirty = command(
            [
                "git",
                "-C",
                source,
                "status",
                "--porcelain",
                "--untracked-files=normal",
                "--",
                ".",
                ":(exclude).gitignore",
            ],
            timeout=5,
        )
        revision = command(["git", "-C", source, "rev-parse", "HEAD"], timeout=5).strip()
        return revision if not dirty.strip() and re.fullmatch(r"[0-9a-f]{40}", revision) else None
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return None


def build_wheel(source, python, work):
    wheels = work / "wheels"
    env = dict(os.environ, CODEX_BOOTSTRAP_DISABLE_RUNTIME="1")
    command(
        [
            python,
            "-B",
            "-m",
            "pip",
            "wheel",
            "--disable-pip-version-check",
            "--no-input",
            "--no-deps",
            "--wheel-dir",
            wheels,
            source,
        ],
        timeout=240,
        env=env,
    )
    found = list(wheels.glob("codex_repo_auto_bootstrap-*.whl"))
    if len(found) != 1:
        raise ValueError("expected one bootstrap wheel")
    return found[0]


def _extract_wheel(wheel, target):
    total = 0
    with zipfile.ZipFile(wheel) as archive:
        for index, item in enumerate(archive.infolist()):
            relative = _relative(item.filename)
            if index >= 5000 or item.external_attr >> 16 & 0o170000 == 0o120000:
                raise ValueError("unsupported wheel member")
            first = relative.parts[0]
            if first != "codex_bootstrap" and not (
                first.startswith("codex_repo_auto_bootstrap-") and first.endswith(".dist-info")
            ):
                raise ValueError("wheel contains unrelated packages")
            total += item.file_size
            if total > 64_000_000:
                raise ValueError("wheel exceeds budget")
            path = target.joinpath(*relative.parts)
            if item.is_dir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(item))
    if not (target / "codex_bootstrap/cli.py").is_file():
        raise ValueError("wheel contains no bootstrap CLI")


def recover_pending(base):
    path = state_directory(base) / "pending.json"
    if not path.exists():
        return
    pending = read_json(path, 16_000_000)
    record_path = base / "installation.json"
    current_hash = digest(record_path)
    if current_hash == pending.get("new_record_hash"):
        path.unlink()
        return
    if current_hash != pending.get("old_record_hash"):
        raise ValueError("update recovery conflicts with modified installation metadata")
    revision = pending.get("commit", "")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("invalid pending update")
    prefix = "venv/versions/" + revision
    record = read_json(record_path)
    if any(name.startswith(prefix + "/") for name in record["files"]):
        raise ValueError("pending update overlaps an owned version")
    target = base / prefix
    if target.exists():
        if target.is_symlink() or not target.resolve().is_relative_to(base.resolve()):
            raise ValueError("unsafe recovery target")
        actual = {}
        for file in target.rglob("*"):
            if file.is_symlink():
                raise ValueError("unsafe recovery link")
            if file.is_file():
                actual[file.relative_to(base).as_posix()] = digest(file)
        if actual != pending.get("new_files"):
            raise ValueError("pending update contains modified files")
        shutil.rmtree(target)
    path.unlink()


def publish_wheel(base, record, wheel, revision, work):
    relative = "venv/versions/" + revision
    if record.get("runtime_path") == relative and record.get("source_commit") == revision:
        return
    target = base / relative
    new_record = dict(record)
    new_record.update(
        source_commit=revision,
        runtime_path=relative,
        previous_commit=record.get("source_commit"),
        previous_runtime_path=record.get("runtime_path"),
    )
    if not target.exists():
        staged = work / "package"
        _extract_wheel(wheel, staged)
        python = record["python"]
        command(
            [
                python,
                "-I",
                "-B",
                "-c",
                "import compileall,sys; assert compileall.compile_dir(sys.argv[1],ddir=sys.argv[2],quiet=1)",
                staged,
                target,
            ],
            timeout=30,
        )
        command(
            [
                python,
                "-I",
                "-B",
                "-c",
                "import sys;sys.path.insert(0,sys.argv[1]);import codex_bootstrap.cli",
                staged,
            ],
            timeout=30,
        )
        additions = {
            relative + "/" + p.relative_to(staged).as_posix(): digest(p)
            for p in staged.rglob("*")
            if p.is_file()
        }
        new_record["files"] = {**record["files"], **additions}
        data = json_text(new_record)
        pending = {
            "commit": revision,
            "old_record_hash": digest(base / "installation.json"),
            "new_record_hash": hashlib.sha256(data.encode()).hexdigest(),
            "new_files": additions,
        }
        atomic_write(state_directory(base) / "pending.json", json_text(pending))
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staged, target)
        atomic_write(base / "installation.json", data)
        (state_directory(base) / "pending.json").unlink()
    else:
        prefix = relative + "/"
        if target.is_symlink() or not any(p.startswith(prefix) for p in record["files"]):
            raise ValueError("unowned existing runtime")
        atomic_write(base / "installation.json", json_text(new_record))


def installation_conflicts(base, record):
    from .installer import _validate_files

    conflicts = _validate_files(base, record["files"], record.get("links"))
    # Uninstall may safely tolerate absent artifacts; activating a runtime cannot.
    for name in (*record["files"], *(record.get("links") or {})):
        if not (base / name).exists():
            conflicts.append(name + ": missing artifact")
    return conflicts


def update(home=None, *, fetcher=None, builder=None, force=False, automatic=False, now=None):
    base = installation_base(home)
    now = time.time() if now is None else now
    acquired = False
    if os.environ.get("CODEX_BOOTSTRAP_OFFLINE") == "1":
        return {"status": "offline"}
    try:
        with installation_mutex(base, timeout=0):
            acquired = True
            recover_pending(base)
            current = status(home)
            if not current["installed"]:
                return {"status": "not-installed"}
            if automatic and not current["enabled"]:
                return {"status": "disabled"}
            if automatic and now < current["next_check"]:
                return {"status": "not-due"}
            record = _record(base)
            if installation_conflicts(base, record):
                _save_state(base, last_result="conflict", next_check=now + RETRY)
                return {"status": "conflict"}
            _save_state(base, last_attempt=now, next_check=now + RETRY)
            revision = latest_commit(fetcher)
            if revision == record.get("source_commit") and not force:
                _save_state(base, last_result="current", last_error=None, next_check=now + INTERVAL)
                return {"status": "current", "commit": revision}
            directory = state_directory(base)
            with tempfile.TemporaryDirectory(prefix="update-", dir=directory) as temporary:
                work = Path(temporary)
                wheel = None
                if not (base / "venv/versions" / revision).exists():
                    data = (fetcher or fetch)(
                        f"https://codeload.github.com/{REPOSITORY}/tar.gz/{revision}", 32_000_000
                    )
                    source = extract_source(data, work / "source")
                    wheel = (builder or build_wheel)(source, record["python"], work)
                if automatic and not status(home)["enabled"]:
                    return {"status": "disabled"}
                publish_wheel(base, record, wheel, revision, work)
            _save_state(base, last_result="updated", last_error=None, next_check=now + INTERVAL)
            return {"status": "updated", "commit": revision}
    except (
        OSError,
        ValueError,
        RuntimeError,
        subprocess.SubprocessError,
        tarfile.TarError,
        zipfile.BadZipFile,
    ) as error:
        if isinstance(error, TimeoutError) and not acquired:
            return {"status": "busy"}
        try:
            with installation_mutex(base, timeout=0):
                recover_pending(base)
                _save_state(
                    base,
                    last_result="failed",
                    last_error=type(error).__name__,
                    next_check=now + RETRY,
                )
        except (OSError, ValueError, RuntimeError):
            pass
        return {"status": "failed", "error": type(error).__name__}


def maybe_schedule_update(home=None):
    try:
        base = installation_base(home)
        if (
            os.environ.get("CODEX_BOOTSTRAP_AUTO_UPDATE") == "0"
            or os.environ.get("CODEX_BOOTSTRAP_OFFLINE") == "1"
        ):
            return False
        if not Path(__file__).resolve().is_relative_to(base) or not Path(
            sys.executable
        ).resolve().is_relative_to(base):
            return False
        current = status(home)
        if (
            not current["installed"]
            or not current["enabled"]
            or time.time() < current["next_check"]
        ):
            return False
        subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-B",
                "-m",
                "codex_bootstrap.self_update",
                "--worker",
                "--home",
                str(base.parents[2]),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=base.parent,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            start_new_session=os.name != "nt",
            env=dict(os.environ, CODEX_BOOTSTRAP_AUTO_UPDATE="0"),
        )
        return True
    except (OSError, ValueError, RuntimeError):
        return False


def rollback(home=None):
    base = installation_base(home)
    with installation_mutex(base):
        recover_pending(base)
        record = _record(base)
        if record is None or "previous_commit" not in record:
            return {"status": "no-previous-version"}
        if installation_conflicts(base, record):
            return {"status": "conflict"}
        old_commit, old_path = record.get("source_commit"), record.get("runtime_path")
        record.update(
            source_commit=record["previous_commit"],
            runtime_path=record.get("previous_runtime_path"),
            previous_commit=old_commit,
            previous_runtime_path=old_path,
        )
        atomic_write(base / "installation.json", json_text(record))
        _save_state(base, enabled=False, last_result="rolled-back", next_check=0)
        return {"status": "rolled-back", "commit": record["source_commit"]}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--home", type=Path)
    options = parser.parse_args(argv)
    result = update(options.home, automatic=True)
    return (
        0
        if result["status"] in {"current", "updated", "not-due", "disabled", "offline", "busy"}
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
