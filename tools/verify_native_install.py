"""Verify an installed distribution with actual, pinned Codex; never call inference.

Use --artifact twice (one wheel, one sdist) to install each in its own fresh venv.
No source directory is added to sys.path. Native execution is mandatory: a missing
binary, incompatible version, subprocess failure or empty catalog fails the run.
"""

import argparse
import glob
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

PROMPT = "Inspect only this project's manifests. Do not execute commands."


def isolated_environment(home):
    env = dict(os.environ)
    for key in list(env):
        if any(word in key.upper() for word in ("TOKEN", "API_KEY", "SECRET", "PASSWORD")):
            env.pop(key, None)
    for key in (
        "PYTHONPATH",
        "PYTHONHOME",
        "CODEX_BOOTSTRAP_ACTIVE",
        "CODEX_BOOTSTRAP_LOCK",
        "CODEX_BOOTSTRAP_REAL_CODEX",
    ):
        env.pop(key, None)
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "CODEX_HOME": str(home / ".codex"),
            "APPDATA": str(home / "appdata"),
            "LOCALAPPDATA": str(home / "localappdata"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "PYTHONNOUSERSITE": "1",
            "CODEX_BOOTSTRAP_OFFLINE": "1",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INPUT": "1",
            "PIP_CACHE_DIR": str(home / ".cache/pip"),
        }
    )
    if os.name == "nt":
        env["HOMEDRIVE"], env["HOMEPATH"] = os.path.splitdrive(str(home))
    return env


def sanitized(message, temporary=None):
    # Useful failure messages without dumping native context or credentials.
    replacements = [(Path.home(), "<HOME>")]
    if temporary:
        replacements.insert(0, (Path(temporary), "<TEMP>"))
    for path, label in replacements:
        for value in (str(path), path.as_posix(), json.dumps(str(path))[1:-1]):
            message = message.replace(value, label)
    message = re.sub(
        r"\b(?:sk-[\w-]{12,}|gh[pousr]_[\w]{12,}|github_pat_[\w]{12,})", "<REDACTED>", message
    )
    message = re.sub(r"(https?://)[^/\s:@]+:[^/\s@]+@", r"\1<REDACTED>@", message)
    message = re.sub(r"(?i)(authorization:\s*(?:Bearer|Basic)\s+)\S+", r"\1<REDACTED>", message)
    message = re.sub(
        r"[A-Za-z]:[\\/]Users[\\/][^\s\"']+|/(?:home|Users)/[^\s\"']+", "<USER_PATH>", message
    )
    return message[-4000:]


def run(command, *, cwd, env, timeout=90):
    try:
        result = subprocess.run(
            [str(value) for value in command],
            cwd=cwd,
            env=env,
            timeout=timeout,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{Path(str(command[0])).name} exceeded {timeout}s timeout") from exc
    if result.returncode:
        detail = sanitized(result.stderr or result.stdout, cwd)
        raise RuntimeError(f"{Path(str(command[0])).name} exited {result.returncode}: {detail}")
    return result.stdout


def catalog(data, cwd):
    """Parse actual native skill entries, retaining duplicates for validation."""
    if not isinstance(data, list):
        raise ValueError("native prompt-input must produce a JSON array")
    names, paths = [], []
    for message in data:
        for part in message.get("content", []):
            text = part.get("text", "")
            for section in re.findall(
                r"<skills_instructions>.*?</skills_instructions>", text, re.S
            ):
                aliases = dict(re.findall(r"^- `([^`]+)` = `([^`]+)`$", section, re.M))
                for line in section.splitlines():
                    if not line.startswith("- ") or "(file:" not in line:
                        continue
                    match = re.fullmatch(r"- (.+?): .*\(file: (.+)\)", line)
                    if not match:
                        raise ValueError("unrecognized native skill catalog entry")
                    name, value = match.groups()
                    value = value.replace("\\", "/")
                    alias, separator, suffix = value.partition("/")
                    if separator and alias in aliases:
                        value = aliases[alias].replace("\\", "/").rstrip("/") + "/" + suffix
                    path = Path(value)
                    paths.append(
                        (cwd / path).resolve() if not path.is_absolute() else path.resolve()
                    )
                    names.append(name)
    if not paths:
        raise ValueError("native skill catalog is empty; native checks cannot be skipped")
    if len(paths) != len(set(paths)) or len(names) != len(set(names)):
        raise ValueError("native skill catalog contains duplicate paths or names")
    return paths


def assert_catalog(data, root, cwd, lock, enabled):
    observed = set(catalog(data, cwd))
    expected = {(root / skill["discovery_path"]).resolve() for skill in enabled}
    if observed != expected:
        missing = len(expected - observed)
        unexpected = len(observed - expected)
        raise ValueError(
            f"native catalog differs from lock: {missing} missing, {unexpected} unexpected"
        )
    if not all(path.is_file() for path in observed):
        raise ValueError("native skill catalog references a missing file")
    if cwd == root / "backend":
        forbidden = {
            (root / skill["discovery_path"]).resolve()
            for skill in lock["skills"]
            if skill["slot"] == "framework-react"
        }
        if not forbidden or observed & forbidden:
            raise ValueError("Rust scope must exclude root/frontend React skills")
    return len(observed)


def snapshot(root, relatives):
    result = {}
    for relative in sorted(set(relatives)):
        path = root / relative
        if not path.is_file():
            raise ValueError("snapshot file missing")
        result[relative] = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
    return result


def verify_user_install(home, root, codex, env):
    """Exercise real platform shims while injecting every user-level OS boundary."""
    from codex_bootstrap.installer import install, uninstall

    class MemoryRegistry:
        value = ("original-tools", 1)

        def read_path(self):
            return self.value

        def write_path(self, value, kind):
            self.value = (value, kind)

        def delete_path(self):
            self.value = None

        def notify(self):
            pass

    registry = MemoryRegistry()
    profile = home / "test-shell-profile"
    original = b"# original user setting\r\n"
    profile.write_bytes(original)
    options = dict(
        home=home,
        real=codex,
        source=home,
        platform=os.name,
        profiles=[profile],
        registry=registry,
        package_install=lambda base, source: Path(sys.executable),
    )
    record = install(**options)
    install(**options)
    # The wrapper resolves the installation record in this temporary home.
    run([sys.executable, "-m", "codex_bootstrap", "--version"], cwd=root, env=env)
    result = uninstall(home=home, platform=os.name, registry=registry)
    if result["conflicts"] or profile.read_bytes() != original or record.exists():
        raise ValueError("temporary user uninstall did not restore original profile")
    if os.name == "nt" and registry.value != ("original-tools", 1):
        raise ValueError("temporary Windows PATH adapter was not restored")
    install(**options)
    addition = b"# user edit after installation\r\n"
    with profile.open("ab") as stream:
        stream.write(addition)
    install(**options)
    result = uninstall(home=home, platform=os.name, registry=registry)
    if result["conflicts"] or profile.read_bytes() != original + addition:
        raise ValueError("temporary user update/uninstall lost later profile edits")
    if uninstall(home=home, platform=os.name, registry=registry)["status"] != "not-installed":
        raise ValueError("temporary user uninstall is not idempotent")


def native_check(codex, expected_version, directory):
    # Imported only inside the selected installed interpreter.
    import codex_bootstrap
    from codex_bootstrap.bootstrap import bootstrap
    from codex_bootstrap.config import active_scope, enabled_skills, launch_profile

    module = Path(codex_bootstrap.__file__).resolve()
    if not module.is_relative_to(Path(sys.prefix).resolve()) or "site-packages" not in module.parts:
        raise ValueError(
            "native verifier requires an installed package in this interpreter's site-packages"
        )
    home, root = directory / "home", directory / "repository"
    home.mkdir()
    root.mkdir()
    env = isolated_environment(home)
    os.environ.clear()
    os.environ.update(env)
    version = run([codex, "--version"], cwd=root, env=env).strip()
    if version != "codex-cli " + expected_version:
        raise ValueError(f"expected Codex {expected_version}, received {sanitized(version)}")
    verify_user_install(home, root, codex, env)
    run(["git", "init", "-q", str(root)], cwd=directory, env=env)
    for scope in (root, root / "frontend"):
        scope.mkdir(exist_ok=True)
        (scope / "package.json").write_text(
            json.dumps({"dependencies": {"react": "^18.3.0"}}), encoding="utf-8"
        )
    (root / "backend").mkdir()
    (root / "backend/Cargo.toml").write_text(
        '[package]\nname="backend"\nversion="0.1.0"\nedition="2021"\n', encoding="utf-8"
    )
    lock = bootstrap(root, offline=True, cache_dir=home / "cache")
    root_react = [
        skill
        for skill in lock["skills"]
        if skill["slot"] == "framework-react" and skill.get("scope", ".") == "."
    ]
    rust = [skill for skill in lock["skills"] if skill.get("scope") == "backend"]
    if not root_react or not rust:
        raise ValueError("native fixture must select root React and backend Rust skills")
    counts = {}
    for scope in (".", "frontend", "backend"):
        cwd = root / scope
        args = ["-C", str(cwd), "debug", "prompt-input", PROMPT]
        with launch_profile(root, lock, args, cwd) as native_args:
            output = run([codex, *native_args], cwd=cwd, env=env)
        counts[scope] = assert_catalog(
            json.loads(output), root, cwd, lock, enabled_skills(lock, active_scope(root, lock, cwd))
        )
    rust_prefixes = tuple(
        str(Path(skill[key]).parent).replace("\\", "/") + "/"
        for skill in rust
        for key in ("path", "discovery_path")
    )
    unchanged = [relative for relative in lock["files"] if relative.startswith(rust_prefixes)]
    unchanged += [
        relative
        for relative in lock["files"]
        if relative.startswith((".codex/bin/", ".codex/tools/", ".codex/plugins/"))
    ]
    if not any(relative.startswith(".codex/bin/") for relative in unchanged):
        raise ValueError("native fixture must include local token tool launchers")
    before = snapshot(root, unchanged)
    (root / "frontend/package.json").write_text(
        '{"dependencies":{"react":"^19.0.0"}}', encoding="utf-8"
    )
    updated = bootstrap(root, offline=True, cache_dir=home / "cache")
    if before != snapshot(root, unchanged):
        raise ValueError("targeted React refresh changed Rust skill/tool content or timestamps")
    if lock["manifest_hashes"] == updated["manifest_hashes"]:
        raise ValueError("React manifest update was not observed")
    changed_slots = {
        key
        for key in set(lock["slot_inputs"]) | set(updated["slot_inputs"])
        if lock["slot_inputs"].get(key) != updated["slot_inputs"].get(key)
    }
    if not changed_slots or any(not key.startswith("frontend::") for key in changed_slots):
        raise ValueError("React update must change only frontend slot inputs")
    cwd = root / "frontend"
    with launch_profile(
        root, updated, ["-C", str(cwd), "debug", "prompt-input", PROMPT], cwd
    ) as native_args:
        output = run([codex, *native_args], cwd=cwd, env=env)
    assert_catalog(
        json.loads(output),
        root,
        cwd,
        updated,
        enabled_skills(updated, active_scope(root, updated, cwd)),
    )
    if list((home / ".codex").glob("auto-bootstrap-*.config.toml")):
        raise ValueError("temporary launch profile was not removed")
    return {
        "package_version": codex_bootstrap.__version__,
        "codex_version": expected_version,
        "native_catalog_counts": counts,
        "preserved_files": len(before),
        "temporary_user_install_reversed": True,
        "user_os_boundaries": "injected adapters in temporary home",
        "platform": sys.platform,
        "python": platform.python_version(),
        "inference_requests": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--expected-codex-version", default="0.166.0")
    parser.add_argument("--artifact", action="append", type=Path, default=[])
    args = parser.parse_args(argv)
    codex = shutil.which(args.codex)
    if not codex:
        parser.exit(1, "native verification failed: Codex executable is required (no skip)\n")
    codex = str(Path(codex).resolve())
    try:
        with tempfile.TemporaryDirectory(prefix="auto-skills-native-") as temporary:
            # macOS exposes its temporary directory through the /var alias.
            # Keep home, repository, venv and native catalog paths canonical.
            directory = Path(temporary).resolve()
            if args.artifact:
                records = []
                artifacts = []
                for path in args.artifact:
                    matches = (
                        [Path(value) for value in glob.glob(str(path))]
                        if glob.has_magic(str(path))
                        else [path]
                    )
                    if not matches:
                        raise ValueError("artifact pattern matched no files")
                    artifacts.extend(matches)
                for index, artifact in enumerate(artifacts):
                    artifact = artifact.resolve(strict=True)
                    environment = directory / f"venv-{index}"
                    venv.EnvBuilder(with_pip=True).create(environment)
                    python = environment / (
                        "Scripts/python.exe" if os.name == "nt" else "bin/python"
                    )
                    home = directory / f"install-home-{index}"
                    home.mkdir()
                    env = isolated_environment(home)
                    run(
                        [python, "-m", "pip", "install", "--no-deps", str(artifact)],
                        cwd=directory,
                        env=env,
                        timeout=240,
                    )
                    # An absolute script location does not expose the source package.
                    output = run(
                        [
                            python,
                            Path(__file__).resolve(),
                            "--codex",
                            codex,
                            "--expected-codex-version",
                            args.expected_codex_version,
                        ],
                        cwd=directory,
                        env=env,
                        timeout=300,
                    )
                    record = json.loads(output)
                    record["artifact"] = artifact.name
                    record["artifact_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
                    records.append(record)
                print(json.dumps(records, indent=2))
            else:
                print(
                    json.dumps(
                        native_check(codex, args.expected_codex_version, directory), indent=2
                    )
                )
    except (OSError, ValueError, RuntimeError, ImportError, subprocess.SubprocessError) as exc:
        parser.exit(1, "native verification failed: " + sanitized(str(exc)) + "\n")


if __name__ == "__main__":
    main()
