"""Install verified RTK releases and pinned Repomix, with useful built-in fallbacks."""

import hashlib
import io
import json
import os
import platform
import re
import shlex
import shutil
import tarfile
import urllib.request
import zipfile
from pathlib import Path

from . import map_runtime, token_runtime
from .fs import atomic_write, command, digest, json_text
from .github import GitHub, safe_resource_path
from .selection import compatible

IGNORE = """# Consumed by token tooling; native Codex support is not assumed.
.git/
.codex/
.agents/
node_modules/
vendor/
.venv/
venv/
dist/
build/
target/
coverage/
.next/
__pycache__/
*.min.js
*.map
*.log
*.lock
package-lock.json
pnpm-lock.yaml
yarn.lock
.env
.env.*
*.pem
*.key
"""


def download(url, max_bytes=100_000_000):
    # Never forward GitHub tokens through release redirects or to registries.
    if not url.startswith("https://"):
        raise ValueError("HTTPS required")
    req = urllib.request.Request(url, headers={"User-Agent": "codex-auto-bootstrap/1"})
    with urllib.request.urlopen(req, timeout=45) as stream:
        data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("download budget exceeded")
    return data


def extract_regular(data, destination, max_expanded=300_000_000):
    """Never use extractall: reject links, devices, traversal, ADS and zip bombs."""
    total, count = 0, 0
    if zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = [
                (
                    e.filename,
                    e.file_size,
                    bool((e.external_attr >> 16) & 0o111),
                    lambda e=e: archive.read(e),
                )
                for e in archive.infolist()
                if not e.is_dir()
            ]
            for name, size, executable, read in entries:
                mode = archive.getinfo(name).external_attr >> 16
                if (mode & 0o170000) == 0o120000:
                    raise ValueError("archive symlink rejected")
                safe_resource_path(name)
                total, count = total + size, count + 1
                if total > max_expanded or count > 20000:
                    raise ValueError("archive expansion budget exceeded")
                atomic_write(destination / name, read(), executable=executable)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
            for entry in archive:
                safe_resource_path(entry.name)
                if entry.isdir():
                    continue
                # Node's npm/npx symlinks aren't needed: npm-cli.js is invoked directly.
                if entry.issym() or entry.islnk():
                    continue
                if not entry.isfile():
                    raise ValueError("archive special file rejected")
                total, count = total + entry.size, count + 1
                if total > max_expanded or count > 20000:
                    raise ValueError("archive expansion budget exceeded")
                stream = archive.extractfile(entry)
                with stream:
                    atomic_write(
                        destination / entry.name, stream.read(), executable=bool(entry.mode & 0o111)
                    )


def write_launcher(bin_dir, name, argv):
    """Use a Python launcher on Windows to preserve argv without cmd interpolation."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = (
        "#!/usr/bin/env python3\nimport os,subprocess,sys\n"
        "from pathlib import Path\nroot=Path(__file__).resolve().parents[2]\n"
        f"args={argv!r}\n"
        "args=[str(root/a[5:]) if a.startswith('REPO:') else a for a in args]\n"
        "raise SystemExit(subprocess.call(args+sys.argv[1:]))\n"
    )
    atomic_write(bin_dir / (name + ".py"), script, executable=True)
    atomic_write(
        bin_dir / name,
        "#!/bin/sh\nexec "
        + shlex.quote(shutil.which("python3") or shutil.which("python") or "python3")
        + ' "$(dirname "$0")/'
        + name
        + '.py" "$@"\n',
        executable=True,
    )
    atomic_write(
        bin_dir / (name + ".cmd"),
        '@echo off\r\n"'
        + os.sys.executable
        + '" "%~dp0'
        + name
        + '.py" %*\r\nexit /b %errorlevel%\r\n',
    )


def install_rtk(stage, github):
    machine = {"amd64": "x86_64", "x86_64": "x86_64", "arm64": "aarch64", "aarch64": "aarch64"}.get(
        platform.machine().lower()
    )
    system = platform.system()
    target = {
        "Windows": "pc-windows-msvc",
        "Darwin": "apple-darwin",
        "Linux": "unknown-linux-musl",
    }.get(system)
    if machine == "aarch64" and system == "Linux":
        target = "unknown-linux-gnu"
    if not machine or not target:
        raise ValueError("unsupported RTK platform")
    release = github.api("repos/rtk-ai/rtk/releases/latest")
    suffix = ".zip" if system == "Windows" else ".tar.gz"
    expected = f"rtk-{machine}-{target}{suffix}"
    asset = next((a for a in release["assets"] if a["name"] == expected), None)
    if asset is None:
        raise ValueError("no RTK binary for this platform")
    data = download(asset["browser_download_url"], 40_000_000)
    checksum = asset.get("digest", "")
    if not checksum.startswith("sha256:"):
        checksums = next(a for a in release["assets"] if a["name"] == "checksums.txt")
        text = download(checksums["browser_download_url"], 200_000).decode()
        line = next(line for line in text.splitlines() if line.split()[-1].lstrip("*") == expected)
        checksum = "sha256:" + line.split()[0]
    if "sha256:" + hashlib.sha256(data).hexdigest() != checksum:
        raise ValueError("RTK archive checksum mismatch")
    unpack = stage / "plugins/rtk/archive"
    extract_regular(data, unpack, 100_000_000)
    name = "rtk.exe" if system == "Windows" else "rtk"
    binaries = list(unpack.rglob(name))
    if len(binaries) != 1:
        raise ValueError("RTK release contains ambiguous binaries")
    binary = stage / "bin" / name
    atomic_write(binary, binaries[0].read_bytes(), executable=True)
    command([binary, "--version"], timeout=15)
    # Archive copies aren't needed at runtime; never remove paths outside the private stage.
    if not unpack.resolve().is_relative_to(stage.resolve()) or unpack.resolve() == stage.resolve():
        raise ValueError("RTK stage cleanup escaped its installation directory")
    shutil.rmtree(unpack)
    return {
        "name": "rtk",
        "slot": "tool-output-compression",
        "status": "installed",
        "version": release["tag_name"],
        "path": ".codex/bin/" + name,
        "repository": "rtk-ai/rtk",
        "archive_sha256": checksum[7:],
        "sha256": digest(binary),
    }


def node_runtime(stage, required=">=22.0.0"):
    node, npm = shutil.which("node"), shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if node and npm:
        version = command([node, "--version"]).strip()
        if any(
            compatible(version, branch.replace(" ", ",").strip(","))
            for branch in required.split("||")
        ):
            return [npm], node, {}
    index = json.loads(download("https://nodejs.org/dist/index.json", 500_000))
    release = next(item for item in index if item.get("lts"))
    arch = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(
        platform.machine().lower()
    )
    system = {"Windows": "win", "Linux": "linux", "Darwin": "darwin"}.get(platform.system())
    if not system or not arch:
        raise ValueError("unsupported Node platform")
    version = release["version"]
    filename = f"node-{version}-{system}-{arch}" + (".zip" if system == "win" else ".tar.gz")
    prefix = f"https://nodejs.org/dist/{version}/"
    sums = download(prefix + "SHASUMS256.txt", 100_000).decode()
    expected = next(line.split()[0] for line in sums.splitlines() if line.split()[-1] == filename)
    data = download(prefix + filename)
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Node archive checksum mismatch")
    destination = stage / "plugins/node"
    extract_regular(data, destination)
    folder = destination / filename.removesuffix(".zip").removesuffix(".tar.gz")
    node = folder / ("node.exe" if system == "win" else "bin/node")
    npm = folder / (
        "node_modules/npm/bin/npm-cli.js"
        if system == "win"
        else "lib/node_modules/npm/bin/npm-cli.js"
    )
    return (
        [str(node), str(npm)],
        str(node),
        {
            "name": "node",
            "slot": "tool-node-runtime",
            "status": "installed",
            "version": version,
            "path": ".codex/" + node.relative_to(stage).as_posix(),
            "archive_sha256": expected,
        },
    )


def install_repomix(stage):
    metadata = json.loads(download("https://registry.npmjs.org/repomix/latest", 2_000_000))
    version = metadata["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[\w.-]+)?", version):
        raise ValueError("invalid Repomix registry version")
    repository = metadata.get("repository", {})
    repo_url = repository.get("url", "") if isinstance(repository, dict) else repository
    if not repo_url.endswith(("github.com/yamadashy/repomix.git", "github.com/yamadashy/repomix")):
        raise ValueError("unexpected Repomix publisher repository")
    npm, node, runtime = node_runtime(stage, metadata.get("engines", {}).get("node", ">=22.0.0"))
    prefix = stage / "plugins/repomix"
    env = dict(
        os.environ,
        CI="1",
        npm_config_update_notifier="false",
        npm_config_ignore_scripts="true",
        npm_config_registry="https://registry.npmjs.org/",
    )
    env["PATH"] = str(Path(node).parent) + os.pathsep + env.get("PATH", "")
    command(
        [
            *npm,
            "install",
            "--prefix",
            str(prefix),
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            "--package-lock=true",
            "--save-exact",
            "--registry=https://registry.npmjs.org/",
            f"repomix@{version}",
        ],
        timeout=300,
        env=env,
    )
    package = prefix / "node_modules/repomix/package.json"
    installed = json.loads(package.read_text(encoding="utf-8"))
    if installed.get("version") != version:
        raise ValueError("Repomix version mismatch")
    lock = json.loads((prefix / "package-lock.json").read_text())
    pinned = lock["packages"]["node_modules/repomix"]
    if pinned.get("integrity") != metadata["dist"].get("integrity"):
        raise ValueError("Repomix registry integrity mismatch")
    entry = installed["bin"]
    entry = entry["repomix"] if isinstance(entry, dict) else entry
    safe_resource_path(entry)
    js = "REPO:.codex/plugins/repomix/node_modules/repomix/" + entry.removeprefix("./")
    node_arg = "REPO:.codex/" + Path(node).relative_to(stage).as_posix() if runtime else node
    write_launcher(
        stage / "bin",
        "repomix",
        [node_arg, js, "--config", "REPO:.codex/plugins/repomix/repomix.config.json"],
    )
    atomic_write(
        prefix / "repomix.config.json",
        json_text(
            {
                "output": {
                    "filePath": ".codex/repomix-output.xml",
                    "style": "xml",
                    "compress": True,
                },
                "ignore": {
                    "useGitignore": True,
                    "customPatterns": [".codex/**", ".agents/**", ".env*", "**/*.pem", "**/*.key"],
                },
                "security": {"enableSecurityCheck": True},
            }
        ),
    )
    command(
        [
            node,
            str(package.parent / entry),
            "--config",
            str(prefix / "repomix.config.json"),
            "--version",
        ],
        env=env,
        timeout=30,
    )
    tool = {
        "name": "repomix",
        "slot": "tool-repo-export",
        "status": "installed",
        "version": version,
        "path": ".codex/bin/repomix.py",
        "repository": "yamadashy/repomix",
        "integrity": pinned["integrity"],
    }
    return [tool] + ([runtime] if runtime else [])


def install_token_tools(stage: Path, *, offline=False, github=None, enabled=None):
    from .automatic_policy import optional_tools

    permitted_optional = optional_tools()
    bin_dir = stage / "bin"
    for name, module in (("token-run", token_runtime), ("repo-map", map_runtime)):
        atomic_write(
            bin_dir / (name + "-impl.py"), Path(module.__file__).read_bytes(), executable=True
        )
        write_launcher(bin_dir, name, [os.sys.executable, "REPO:.codex/bin/" + name + "-impl.py"])
    tools = [
        {
            "name": "token-run",
            "slot": "tool-terminal-budget",
            "status": "installed",
            "version": "1",
            "path": ".codex/bin/token-run.py",
        },
        {
            "name": "repo-map",
            "slot": "tool-repo-map",
            "status": "installed",
            "version": "1",
            "path": ".codex/bin/repo-map.py",
            "ast_languages": ["python"],
        },
    ]
    for name, install in (
        ("rtk", lambda: [install_rtk(stage, github or GitHub())]),
        ("repomix", lambda: install_repomix(stage)),
    ):
        if enabled is not None and name not in enabled:
            continue
        if name == "repomix" and name not in permitted_optional:
            tools.append(
                {
                    "name": name,
                    "status": "deferred",
                    "reason": "enable automatic.optional_tools=['repomix'] in the user-global auto-skills.toml, then refresh",
                }
            )
            continue
        if offline:
            tools.append({"name": name, "status": "unavailable", "reason": "offline mode"})
            continue
        try:
            tools.extend(install())
        except Exception as exc:
            # Partially installed binaries must never be picked up by token-run or PATH.
            for folder in (
                [stage / "plugins/rtk"]
                if name == "rtk"
                else [stage / "plugins/repomix", stage / "plugins/node"]
            ):
                if folder.exists():
                    if (
                        not folder.resolve().is_relative_to(stage.resolve())
                        or folder.resolve() == stage.resolve()
                    ):
                        raise ValueError("tool cleanup escaped its installation directory") from exc
                    shutil.rmtree(folder)
            for path in bin_dir.glob("rtk*") if name == "rtk" else bin_dir.glob("repomix*"):
                if path.is_file():
                    path.unlink()
            # A degraded lock remains explicit; no fake binary or success entry is generated.
            tools.append(
                {
                    "name": name,
                    "status": "unavailable",
                    "reason": type(exc).__name__,
                    "detail": str(exc)[:200],
                }
            )
    for tool in tools:
        atomic_write(stage / "plugins" / tool["name"] / "plugin.json", json_text(tool))
    return tools
