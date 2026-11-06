"""GitHub CLI first; HTTPS REST fallback supports unauthenticated public discovery."""

import base64
import hashlib
import json
import math
import os
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path, PurePosixPath

from .fs import command

CACHE_OWNER = "codex-auto-bootstrap/github-v1"


class GitHubError(RuntimeError):
    """Sanitized public-discovery failure; never includes upstream stderr or credentials."""


def default_cache_dir():
    """User cache, outside the project; CODEX_BOOTSTRAP_CACHE overrides the location."""
    override = os.environ.get("CODEX_BOOTSTRAP_CACHE")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
    elif os.sys.platform == "darwin":
        root = Path.home() / "Library/Caches"
    else:
        root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "codex-auto-bootstrap" / "github-v1"


class GitHub:
    """Bounded GitHub client with public-only TTL caching.

    ``cache_dir=None`` uses the platform user cache (or CODEX_BOOTSTRAP_CACHE).
    ``offline=True`` serves only unexpired public cache entries. ``transport`` is an
    optional callable receiving a validated endpoint and returning parsed JSON, or
    ``(JSON, headers)``; HTTPError communicates status/retry headers in tests.
    ``clock`` is wall time for TTL/reset headers; ``monotonic`` controls deadlines.
    No credentials, headers, private payloads, or arbitrary API routes are persisted.
    """

    def __init__(
        self,
        *,
        cache_dir=None,
        offline=False,
        transport=None,
        clock=time.time,
        monotonic=time.monotonic,
        sleep=time.sleep,
        cache_entries=512,
        cache_bytes=32_000_000,
        max_requests=180,
        timeout=120,
        max_retries=2,
        max_retry_sleep=2,
    ):
        self.gh = shutil.which("gh")
        self.errors = []
        self.queries = []
        self.stats = {
            "requests": 0,
            "memory_cache_hits": 0,
            "disk_cache_hits": 0,
            "cache_writes": 0,
            "cache_errors": 0,
            "retries": 0,
            "rate_limited": 0,
            "budget_exhausted": 0,
        }
        self.cache_dir = Path(cache_dir) if cache_dir is not None else default_cache_dir()
        self.offline = offline
        self._transport, self._clock, self._monotonic, self._sleep = (
            transport,
            clock,
            monotonic,
            sleep,
        )
        self._cache_entries, self._cache_bytes = cache_entries, cache_bytes
        self._max_requests, self._timeout = max_requests, timeout
        self._max_retries, self._max_retry_sleep = max_retries, max_retry_sleep
        self._cache = {}
        self._mutex = threading.Lock()
        self._disk_mutex = threading.Lock()
        self._local = threading.local()
        self._gh_unavailable = set()
        self._scopes = {}
        self._public = set()
        self._blocked = {}
        self._started = self._monotonic()
        self._requests = 0
        self._auth_mutex = threading.Lock()
        self._gh_auth_checked = False
        self._gh_auth_token = None

    @staticmethod
    def _route(endpoint):
        """Strict allowlist prevents authenticated account/action endpoints being cached."""
        parsed = urllib.parse.urlsplit(endpoint)
        if parsed.scheme or parsed.netloc or parsed.fragment or "\\" in endpoint:
            raise ValueError("unsupported GitHub endpoint")
        search = re.fullmatch(r"search/(repositories|code)", parsed.path)
        query = urllib.parse.parse_qs(parsed.query)
        if search and set(query) <= {"q", "per_page", "page", "sort", "order"}:
            return "search", None
        match = re.fullmatch(
            r"repos/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?:/(releases/latest|commits/[A-Za-z0-9_.%/-]+|git/(?:trees|blobs)/[a-f0-9]{40}))?",
            parsed.path,
        )
        if not match or not set(query) <= {"recursive"}:
            raise ValueError("unsupported GitHub endpoint")
        repository = GitHub.valid_repo(match[1])
        suffix = match[2] or ""
        if suffix == "releases/latest":
            return "release", repository
        return (
            "metadata" if not suffix else "blob" if "/blobs/" in suffix else "snapshot"
        ), repository

    @staticmethod
    def _ttl(kind):
        return {
            "search": 3600,
            "metadata": 1800,
            "snapshot": 86400,
            "blob": 604800,
            "release": 300,
        }[kind]

    def _public_value(self, endpoint, kind, repository, value):
        if kind == "metadata":
            public = isinstance(value, dict) and value.get("private") is False
            if public:
                with self._mutex:
                    self._public.add(repository)
            return public
        if kind == "search":
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(endpoint).query).get("q", [""])[0]
            return (
                "is:public" in query.split()
                and isinstance(value, dict)
                and all(
                    item.get("private") is not True
                    and item.get("repository", {}).get("private") is not True
                    for item in value.get("items", [])
                )
            )
        with self._mutex:
            return repository in self._public

    def _cache_path(self, endpoint):
        return self.cache_dir / (hashlib.sha256(endpoint.encode()).hexdigest() + ".json")

    @staticmethod
    def _public_payload(endpoint, kind, value):
        """Persist only discovery fields, excluding account-specific permissions."""

        def fields(data, names):
            return {name: data[name] for name in names if name in data}

        metadata_fields = (
            "private",
            "archived",
            "disabled",
            "default_branch",
            "full_name",
            "fullName",
            "stargazers_count",
            "stargazersCount",
            "pushed_at",
            "updatedAt",
        )
        if kind == "metadata":
            result = fields(value, metadata_fields)
            license_data = value.get("license")
            if isinstance(license_data, dict):
                result["license"] = fields(license_data, ("spdx_id", "name", "key"))
            return result
        if kind == "search":
            result = fields(value, ("total_count", "incomplete_results"))
            result["items"] = []
            for item in value.get("items", []):
                entry = fields(item, (*metadata_fields, "path"))
                if isinstance(item.get("repository"), dict):
                    entry["repository"] = fields(
                        item["repository"], (*metadata_fields, "nameWithOwner")
                    )
                result["items"].append(entry)
            return result
        if kind == "blob":
            return fields(value, ("sha", "size", "encoding", "content"))
        if kind == "release":
            return {
                "tag_name": value.get("tag_name"),
                "assets": [
                    fields(asset, ("name", "digest", "browser_download_url"))
                    for asset in value.get("assets", [])
                ],
            }
        if "/git/trees/" in endpoint:
            return {
                **fields(value, ("sha", "truncated")),
                "tree": [
                    fields(entry, ("path", "mode", "type", "sha", "size"))
                    for entry in value.get("tree", [])
                ],
            }
        return fields(value, ("sha",))

    def _read_disk(self, endpoint, kind, repository):
        path = self._cache_path(endpoint)
        try:
            if path.stat().st_size > min(self._cache_bytes, 16_100_000):
                return None
            record = json.loads(path.read_text(encoding="utf-8"))
            age = self._clock() - record["fetched"]
            value = record["value"]
            if not self._owned_record(record) or not 0 <= age < self._ttl(kind):
                return None
            if not self._valid_cached_value(endpoint, kind, value):
                return None
            if not self._public_value(endpoint, kind, repository, value):
                return None
            with self._mutex:
                self.stats["disk_cache_hits"] += 1
            return value
        except (OSError, ValueError, KeyError, TypeError):
            return None

    @staticmethod
    def _owned_record(record):
        """An envelope marker distinguishes our files in a shared cache directory."""
        return (
            isinstance(record, dict)
            and record.get("cache_owner") == CACHE_OWNER
            and record.get("schema") == 1
            and isinstance(record.get("fetched"), (int, float))
            and math.isfinite(record["fetched"])
            and isinstance(record.get("value"), dict)
        )

    def _owned_cache_entry(self, path):
        """Only regular hash-named files with our valid envelope may be evicted."""
        if not re.fullmatch(r"[a-f0-9]{64}\.json", path.name):
            return None
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_size > 32_100_000:
                return None
            record = json.loads(path.read_text(encoding="utf-8"))
            if self._owned_record(record):
                return info.st_mtime, path, info.st_size
        except (OSError, ValueError, TypeError):
            pass
        return None

    @staticmethod
    def _valid_cached_value(endpoint, kind, value):
        if not isinstance(value, dict):
            return False
        if kind == "metadata":
            return value.get("private") is False
        if kind == "search":
            return isinstance(value.get("items"), list) and all(
                isinstance(item, dict) and isinstance(item.get("repository", {}), dict)
                for item in value["items"]
            )
        if kind == "blob":
            return (
                value.get("encoding") == "base64"
                and isinstance(value.get("content"), str)
                and isinstance(value.get("size"), int)
                and 0 <= value["size"] <= 16_000_000
            )
        if kind == "release":
            return (
                isinstance(value.get("tag_name"), str)
                and isinstance(value.get("assets"), list)
                and all(
                    isinstance(asset, dict)
                    and isinstance(asset.get("name"), str)
                    and isinstance(asset.get("browser_download_url"), str)
                    and asset["browser_download_url"].startswith("https://")
                    and (asset.get("digest") is None or isinstance(asset["digest"], str))
                    for asset in value["assets"]
                )
            )
        if "/git/trees/" in endpoint:
            return isinstance(value.get("tree"), list) and all(
                isinstance(item, dict)
                and all(isinstance(item.get(key), str) for key in ("path", "sha", "type", "mode"))
                for item in value["tree"]
            )
        return isinstance(value.get("sha"), str) and bool(
            re.fullmatch(r"[a-f0-9]{40}", value["sha"])
        )

    def _write_disk(self, endpoint, value):
        try:
            payload = json.dumps(
                {"cache_owner": CACHE_OWNER, "schema": 1, "fetched": self._clock(), "value": value}
            ).encode()
            if len(payload) > self._cache_bytes or self._cache_entries < 1:
                return
            # Atomic replacement also tolerates overlapping independent invocations.
            with self._disk_mutex:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                target = self._cache_path(endpoint)
                if (target.exists() or target.is_symlink()) and self._owned_cache_entry(
                    target
                ) is None:
                    # A caller may intentionally share this directory with other
                    # software. Even an unlikely hash-name collision is not ours.
                    with self._mutex:
                        self.stats["cache_errors"] += 1
                    return
                fd, temporary = tempfile.mkstemp(prefix=".github-", dir=self.cache_dir)
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(payload)
                    os.replace(temporary, target)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
                entries = sorted(
                    (
                        entry
                        for p in self.cache_dir.glob("*.json")
                        if (entry := self._owned_cache_entry(p)) is not None
                    ),
                    key=lambda item: (item[0], item[1].name),
                )
                size, count = sum(e[2] for e in entries), len(entries)
                for _, path, length in entries:
                    if size <= self._cache_bytes and count <= self._cache_entries:
                        break
                    path.unlink(missing_ok=True)
                    size, count = size - length, count - 1
            with self._mutex:
                self.stats["cache_writes"] += 1
        except (OSError, ValueError, TypeError):
            with self._mutex:
                self.stats["cache_errors"] += 1

    @contextmanager
    def budget_scope(self, name, limit):
        """Share a named network quota across worker threads; cache hits cost nothing."""
        previous = getattr(self._local, "scope", None)
        self._local.scope = (name, limit)
        try:
            yield
        finally:
            self._local.scope = previous

    def remaining_seconds(self):
        """Remaining discovery deadline for bounded CPU work as well as requests."""
        return max(0, self._timeout - (self._monotonic() - self._started))

    def _reserve(self, resource):
        with self._mutex:
            if self._blocked.get(resource, 0) > self._clock():
                raise GitHubError(
                    f"GitHub {resource} rate limit active; cached results remain available"
                )
            scope = getattr(self._local, "scope", None)
            if (
                self._requests >= self._max_requests
                or self._monotonic() - self._started >= self._timeout
                or (scope and self._scopes.get(scope[0], 0) >= scope[1])
            ):
                self.stats["budget_exhausted"] += 1
                raise GitHubError(
                    "GitHub discovery request/time budget exhausted; using available candidates"
                )
            self._requests += 1
            self.stats["requests"] += 1
            if scope:
                self._scopes[scope[0]] = self._scopes.get(scope[0], 0) + 1

    def _retry_delay(self, headers, attempt):
        headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
        try:
            value = headers.get("retry-after")
            if value:
                try:
                    return max(0, float(value))
                except ValueError:
                    return max(0, parsedate_to_datetime(value).timestamp() - self._clock())
            if headers.get("x-ratelimit-remaining") == "0":
                return max(0, float(headers.get("x-ratelimit-reset", 0)) - self._clock())
        except (ValueError, TypeError, OverflowError):
            pass
        return float(2**attempt)

    def _request(self, endpoint, resource):
        family = urllib.parse.urlsplit(endpoint).path if endpoint.startswith("search/") else "core"
        with self._mutex:
            use_gh = bool(
                self.gh and self._transport is None and family not in self._gh_unavailable
            )
        for attempt in range(self._max_retries + 1):
            self._reserve(resource)
            try:
                if use_gh:
                    use_gh = False
                    try:
                        parsed = urllib.parse.urlsplit(endpoint)
                        if parsed.path.startswith("search/"):
                            kind = "repos" if parsed.path == "search/repositories" else "code"
                            parameters = urllib.parse.parse_qs(parsed.query)
                            fields = (
                                "repository,path"
                                if kind == "code"
                                else "fullName,stargazersCount,updatedAt"
                            )
                            args = [
                                self.gh,
                                "search",
                                kind,
                                parameters.get("q", [""])[0],
                                "--limit",
                                str(min(20, max(1, int(parameters.get("per_page", ["5"])[0])))),
                                "--json",
                                fields,
                            ]
                            env = {**os.environ, "GH_HOST": "github.com"}
                        else:
                            args = [self.gh, "api", "--hostname", "github.com", endpoint]
                            env = None
                        value = json.loads(
                            command(
                                args,
                                env=env,
                                timeout=max(
                                    0.1,
                                    min(10, self._timeout - (self._monotonic() - self._started)),
                                ),
                            )
                        )
                        if parsed.path.startswith("search/"):
                            if not isinstance(value, list) or not all(
                                isinstance(item, dict) for item in value
                            ):
                                raise ValueError("invalid GitHub CLI search result")
                            return {"items": value}
                        return value
                    except (
                        OSError,
                        RuntimeError,
                        ValueError,
                        TimeoutError,
                        subprocess.TimeoutExpired,
                    ):
                        # An unauthenticated/missing CLI otherwise spends two
                        # requests for every blob in a multi-file skill. Keep
                        # its credential fallback, but use HTTPS for this family
                        # for the remainder of the bounded discovery operation.
                        with self._mutex:
                            self._gh_unavailable.add(family)
                        self._reserve(resource)
                response = self._transport(endpoint) if self._transport else self._http(endpoint)
                return response[0] if isinstance(response, tuple) else response
            except urllib.error.HTTPError as exc:
                headers = {str(k).lower(): str(v) for k, v in (exc.headers or {}).items()}
                limited = exc.code == 429 or (
                    exc.code == 403
                    and (headers.get("x-ratelimit-remaining") == "0" or "retry-after" in headers)
                )
                transient = limited or exc.code in {500, 502, 503, 504}
                delay = self._retry_delay(headers, attempt)
                if limited:
                    with self._mutex:
                        self.stats["rate_limited"] += 1
                can_retry = (
                    transient
                    and attempt < self._max_retries
                    and delay <= self._max_retry_sleep
                    and self._monotonic() - self._started + delay < self._timeout
                )
                if can_retry:
                    with self._mutex:
                        self.stats["retries"] += 1
                    self._sleep(delay)
                    continue
                if limited:
                    with self._mutex:
                        self._blocked[resource] = self._clock() + max(delay, 60)
                    raise GitHubError(
                        f"GitHub {resource} rate limit reached (HTTP {exc.code}); retry after "
                        f"{datetime.fromtimestamp(self._clock() + max(delay, 1), UTC).isoformat()}; "
                        "using cached/local candidates"
                    ) from None
                if exc.code == 401:
                    reason = "authentication required or rejected; configure gh auth or GH_TOKEN for code search"
                elif exc.code == 403:
                    reason = (
                        "access denied; check token permissions or GitHub secondary rate limits"
                    )
                elif exc.code == 404:
                    reason = "public repository or resource no longer exists"
                else:
                    reason = "GitHub request failed"
                raise GitHubError(f"{reason} (HTTP {exc.code})") from None
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                if attempt < self._max_retries:
                    delay = float(2**attempt)
                    if (
                        delay <= self._max_retry_sleep
                        and self._monotonic() - self._started + delay < self._timeout
                    ):
                        with self._mutex:
                            self.stats["retries"] += 1
                        self._sleep(delay)
                        continue
                raise GitHubError(
                    f"GitHub network request failed ({type(exc).__name__}); check connectivity"
                ) from None
        raise GitHubError("GitHub retry budget exhausted")

    def api(self, endpoint):
        kind, repository = self._route(endpoint)
        with self._mutex:
            cached = self._cache.get(endpoint)
            if cached and 0 <= self._clock() - cached[0] < self._ttl(kind):
                self.stats["memory_cache_hits"] += 1
                return cached[1]
        value = self._read_disk(endpoint, kind, repository)
        if value is None:
            if self.offline:
                raise GitHubError("offline cache miss or expired public cache entry")
            value = self._request(endpoint, "search" if kind == "search" else "core")
            if self._public_value(endpoint, kind, repository, value):
                self._write_disk(endpoint, self._public_payload(endpoint, kind, value))
        with self._mutex:
            self._cache[endpoint] = (self._clock(), value)
        return value

    def _http(self, endpoint):
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "codex-auto-bootstrap/1"}
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token and self.gh:
            # Reuse gh's existing login for an API fallback; never print or persist its token.
            with self._auth_mutex:
                if not self._gh_auth_checked:
                    self._gh_auth_checked = True
                    try:
                        self._gh_auth_token = (
                            command(
                                [self.gh, "auth", "token", "--hostname", "github.com"],
                                timeout=max(0.1, min(5, self.remaining_seconds())),
                            ).strip()
                            or None
                        )
                    except (
                        OSError,
                        RuntimeError,
                        ValueError,
                        TimeoutError,
                        subprocess.TimeoutExpired,
                    ):
                        self._gh_auth_token = None
                token = self._gh_auth_token
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request("https://api.github.com/" + endpoint, headers=headers)
        timeout = max(0.1, min(10, self._timeout - (self._monotonic() - self._started)))
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(16_000_001)
        if len(data) > 16_000_000:
            raise ValueError("GitHub response limit exceeded")
        return json.loads(data)

    def search(self, kind, query, limit=5):
        if kind not in {"repos", "code"}:
            raise ValueError("unsupported GitHub search kind")
        with self._mutex:
            self.queries.append({"kind": kind, "query": query})
        try:
            api_kind = "repositories" if kind == "repos" else "code"
            data = self.api(
                f"search/{api_kind}?"
                + urllib.parse.urlencode(
                    {"q": query + " is:public", "per_page": min(20, max(1, limit))}
                )
            )
            return [
                item
                for item in data.get("items", [])
                if item.get("private") is not True
                and item.get("repository", {}).get("private") is not True
            ]
        except Exception as exc:
            # Only our own sanitized errors are safe to display; transport errors may contain tokens.
            reason = str(exc) if isinstance(exc, GitHubError) else type(exc).__name__
            with self._mutex:
                self.errors.append({"operation": "search-" + kind, "reason": reason})
            return []

    @staticmethod
    def valid_repo(repository):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("invalid repository identifier")
        return repository

    def snapshot(self, repository):
        repository = self.valid_repo(repository)
        meta = self.api(f"repos/{repository}")
        if meta.get("private") is True:
            raise ValueError("private repositories are excluded from public skill discovery")
        if meta.get("archived") or meta.get("disabled"):
            raise ValueError("archived or disabled repository")
        branch = urllib.parse.quote(meta.get("default_branch", "main"), safe="")
        commit = self.api(f"repos/{repository}/commits/{branch}")["sha"]
        if not re.fullmatch(r"[a-f0-9]{40}", commit):
            raise ValueError("invalid commit SHA")
        tree = self.api(f"repos/{repository}/git/trees/{commit}?recursive=1")
        if tree.get("truncated"):
            raise ValueError("truncated repository index")
        return meta, commit, tree["tree"]

    def blob(self, repository, sha, max_size=256_000):
        data = self.api(f"repos/{repository}/git/blobs/{sha}")
        if data.get("size", max_size + 1) > max_size or data.get("encoding") != "base64":
            raise ValueError("unsupported or oversized skill resource")
        content = base64.b64decode(data["content"])
        if len(content) > max_size:
            raise ValueError("oversized resource")
        return content


def safe_resource_path(value):
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in {"..", ".git"} or ":" in p or "\\" in p for p in path.parts):
        raise ValueError("unsafe resource path")
    if any(
        p.endswith((" ", "."))
        or re.fullmatch(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", p, re.I)
        for p in path.parts
    ):
        raise ValueError("nonportable resource path")
    return path
