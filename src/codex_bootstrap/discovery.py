"""Both mandatory search axes plus public skill registries. No project source is sent."""

import json
import posixpath
import re
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from pathlib import PurePosixPath

from .github import GitHub, GitHubError, safe_resource_path
from .profile import BASE_SLOTS
from .selection import Candidate, clean_markdown, rejection

REGISTRIES = [
    "openai/skills",
    "vercel-labs/agent-skills",
    "anthropics/skills",
    "trailofbits/skills",
]
SUPPLEMENTAL_REPOSITORIES = 4
MAX_TERMS_PER_SLOT = 8
MAX_TREE_ENTRIES = 50_000
MAX_SKILL_PATHS = 10_000
_SEPARATORS = str.maketrans("-_/", "   ")
_WORD_CHARACTERS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")
SLOT_TERMS = {
    "token-output-compression": ["token", "compression", "concise output"],
    "token-context-pruning": ["context", "surgical", "partial read"],
    "token-reasoning": ["reasoning_effort", "reasoning effort"],
    "token-prompt-cache": ["prompt caching", "prompt cache"],
    "token-cli-wrapper": ["rtk", "token optimizer"],
    "architecture": ["architecture", "module design"],
    "unit-testing": ["unit testing", "pytest", "vitest", "test-driven"],
    "e2e-testing": ["playwright", "e2e", "cypress"],
    "security": ["security", "secure coding"],
    "performance": ["performance", "optimization"],
    "refactoring": ["refactor"],
    "ci-cd": ["github actions", "ci-cd", "pipeline"],
    "build": ["build", "package manager"],
    "documentation": ["documentation"],
    "static-analysis": ["lint", "typecheck", "static analysis"],
    "containers": ["docker"],
    "infrastructure": ["terraform"],
    "ui-components": ["shadcn", "tailwind", "component"],
    "desktop-tauri": ["tauri"],
    "framework-tauri": ["tauri"],
    "realtime-audio": [
        "realtime audio",
        "real time audio",
        "audio callback",
        "cpal",
        "portaudio",
        "wasapi",
    ],
    "audio-midi": ["midi", "midir"],
    "audio-osc": ["osc", "open sound control", "rosc"],
    "audio-rtp": ["rtp", "rtcp", "rtp midi", "rtpmidi"],
    "audio-vst": ["vst", "vst3", "audio plugin"],
    "platform-windows": ["windows", "win32", "wasapi"],
    "midi": ["midi", "midir"],
    "osc": ["osc", "open sound control", "rosc"],
    "rtp-midi": ["rtp midi", "rtpmidi", "rtp", "rtcp"],
    "audio-plugin-vst": ["vst", "vst3", "audio plugin", "nih_plug"],
    "native-windows": ["windows", "win32", "wasapi"],
    "process-workers": ["worker", "subprocess", "process isolation"],
    "midi-python": ["mido", "python rtmidi", "midi callback"],
    "led-ws281x": ["rpi ws281x", "ws281x", "neopixel"],
    "gpio-python": ["rpi gpio", "gpiozero", "gpio"],
    "platform-raspberry-pi": ["raspberry pi", "raspberry pi systemd", "rpi"],
}
TOKEN_QUERIES = [
    'filename:SKILL.md "token" "compression"',
    'filename:SKILL.md "reasoning_effort"',
    'filename:SKILL.md "prompt caching"',
    'filename:SKILL.md "context" "pruning"',
    'filename:AGENTS.md "rtk"',
    'filename:.cursorrules "token"',
]


def terms_for(slot, profile=None):
    """Prefer technologies assigned to this slot, never all project technologies."""
    semantic = SLOT_TERMS.get(slot, [slot.split("-", 1)[-1]])
    if slot in BASE_SLOTS:
        return semantic[:MAX_TERMS_PER_SLOT]
    scoped = getattr(profile, "slot_technologies", {}).get(slot, []) if profile else []
    if isinstance(scoped, str):
        scoped = [scoped]
    scoped = [
        str(term)
        for term in scoped
        if len(str(term)) <= 80 and re.fullmatch(r"[A-Za-z0-9@_./+-]+", str(term))
    ]
    return list(dict.fromkeys(scoped[: max(0, MAX_TERMS_PER_SLOT - len(semantic))] + semantic))[
        :MAX_TERMS_PER_SLOT
    ]


def _normalize(value):
    return value.lower().translate(_SEPARATORS)


def _contains_term(text, term):
    """Literal ASCII-word boundaries avoid compiling a regex for every dependency."""
    start = text.find(term)
    while start >= 0:
        end = start + len(term)
        if (start == 0 or text[start - 1] not in _WORD_CHARACTERS) and (
            end == len(text) or text[end] not in _WORD_CHARACTERS
        ):
            return True
        start = text.find(term, start + 1)
    return False


def _prepare_matchers(slots, profile=None):
    return tuple(
        (slot, tuple(_normalize(term) for term in terms_for(slot, profile))) for slot in slots
    )


def infer_slot(path, text, slots, profile=None, matchers=None):
    explicit = (
        re.search(r"(?m)^(?:x-bootstrap-slot|slot):\s*[\"']?([a-z0-9-]+)", text) if text else None
    )
    if explicit:
        return explicit[1] if explicit[1] in slots else None
    normalized_path, normalized_text = _normalize(path), _normalize(text[:700])
    matchers = _prepare_matchers(slots, profile) if matchers is None else matchers
    scores = [
        (
            sum(
                4
                if _contains_term(normalized_path, term)
                else int(bool(normalized_text) and _contains_term(normalized_text, term))
                for term in terms
            ),
            slot,
        )
        for slot, terms in matchers
    ]
    value, slot = max(scores, default=(0, ""))
    return slot if value > 0 else None


def normalize_resources(text, files):
    """Repair unique intra-bundle basenames without fetching paths outside the skill."""
    documents = {"SKILL.md": text.encode(), **files}
    for document, content in list(documents.items()):
        if not document.endswith(".md"):
            continue
        original = content.decode("utf-8", errors="replace")
        body = re.sub(r"(?ms)^\s*(`{3,}|~{3,}).*?^\s*\1[^\n]*$", "", original)
        for link in re.findall(r"\]\(([^\s)#]+)(?:#[^)]*)?\)", body):
            if "://" in link or link.startswith(("mailto:", "#")):
                continue
            target = posixpath.normpath(str(PurePosixPath(document).parent / link))
            safe_resource_path(target)
            if target in documents or any(
                k.startswith(target.rstrip("/") + "/") for k in documents
            ):
                continue
            # Some generated rule books refer to unique rules by basename from the root.
            matches = [k for k in documents if PurePosixPath(k).name == PurePosixPath(target).name]
            if len(matches) != 1:
                raise ValueError("missing/ambiguous local skill dependency: " + target)
            replacement = posixpath.relpath(matches[0], str(PurePosixPath(document).parent))
            original = re.sub(
                r"(\]\()" + re.escape(link) + r"(?=[)#\s])",
                lambda m, replacement=replacement: m[1] + replacement,
                original,
            )
        documents[document] = original.encode()
    return documents.pop("SKILL.md").decode(), documents


def candidate_from_tree(
    github, repository, meta, commit, tree, path, slots, profile=None, matchers=None
):
    by_path = {entry["path"]: entry for entry in tree}
    entry = by_path[path]
    if entry.get("mode") != "100644" or entry.get("size", 0) > 24_000:
        raise ValueError("unsupported skill file")
    text = github.blob(repository, entry["sha"], 24_000).decode("utf-8-sig")
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        raise ValueError("not an Agent Skill")
    slot = infer_slot(path, text, slots, profile, matchers)
    if not slot:
        raise ValueError("no relevant functional slot")
    # Structured metadata uses JSON inside YAML, a valid unambiguous YAML subset.
    compatibility = {}
    constraint = re.search(
        r"(?m)^(?:x-bootstrap-compatibility|compatibility):\s*(\{[^\n]+\})", text
    )
    if constraint:
        compatibility = json.loads(constraint[1])
        if not isinstance(compatibility, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in compatibility.items()
        ):
            raise ValueError("invalid compatibility metadata")
    name = re.search(r"(?m)^name:\s*[\"']?([a-zA-Z0-9_-]+)", text)
    candidate = Candidate(
        slot=slot,
        name=name[1] if name else slot,
        body=clean_markdown(text),
        repository=repository,
        commit=commit,
        remote_path=path,
        stars=meta.get("stargazers_count", 0),
        updated=meta.get("pushed_at", ""),
        compatibility=compatibility,
        declared_slot=bool(re.search(r"(?m)^(?:x-bootstrap-slot|slot):", text)),
    )
    if profile is not None:
        # Eligibility based on root instructions is already sufficient to skip
        # unsupported tools/frameworks and avoid downloading entire bundles.
        reason = rejection(candidate, profile)
        if reason:
            raise ValueError(reason)
    parent = PurePosixPath(path).parent
    prefix = str(parent) + "/" if str(parent) != "." else ""
    resources = [
        item
        for item in tree
        if item["path"].startswith(prefix) and item["type"] == "blob" and item["path"] != path
    ]
    # A repository-root SKILL.md does not authorize downloading an entire repository.
    if not prefix:
        resources = []
    if len(resources) > 80 or sum(e.get("size", 0) for e in resources) > 2_000_000:
        raise ValueError("skill resource budget exceeded")
    files, executable_files = {}, set()
    for item in resources:
        relative = item["path"][len(prefix) :]
        safe_resource_path(relative)
        if item.get("mode") not in {"100644", "100755"}:
            raise ValueError("symlink/submodule resource rejected")
        files[relative] = github.blob(repository, item["sha"])
        if item.get("mode") == "100755":
            executable_files.add(relative)
    text, files = normalize_resources(text, files)
    license_id = (meta.get("license") or {}).get("spdx_id", "")
    license_origin = "repository-metadata" if license_id else "unverified"
    frontmatter = text.split("---", 2)[1] if text.startswith("---") else ""
    declaration = re.search(r"(?m)^license:[ \t]*[\"']?([A-Za-z0-9.+-]+)[\"']?[ \t]*$", frontmatter)
    if declaration:
        license_id, license_origin = declaration[1], "skill-frontmatter"
    # Registries commonly license each skill separately and have no repository SPDX metadata.
    for filename, content in files.items():
        if PurePosixPath(filename).name.lower().startswith(("license", "copying")):
            license_text = content.decode("utf-8", errors="replace")
            if "Apache License" in license_text and "Version 2.0" in license_text:
                license_id = "Apache-2.0"
                license_origin = filename
            elif "Permission is hereby granted, free of charge" in license_text:
                license_id = "MIT"
                license_origin = filename
    license_id = license_id or "NOASSERTION"
    for entry_name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING", "NOTICE"):
        if entry_name in by_path and entry_name not in files:
            files["UPSTREAM-" + entry_name] = github.blob(repository, by_path[entry_name]["sha"])
    candidate.body, candidate.files = clean_markdown(text), files
    candidate.license, candidate.executable_files = license_id, executable_files
    candidate.license_origin = license_origin
    return candidate


def discover(
    profile, github=None, *, slots=None, cache_dir=None, offline=False, allowed_repositories=None
):
    """Discover public skills; ``slots`` limits matching/search for incremental refresh.

    ``slots=None`` searches the full profile; an empty iterable does no remote work.
    ``cache_dir`` and ``offline`` configure a newly created GitHub client only.
    Fixture clients need only search/snapshot/blob plus queries/errors attributes.
    """
    github = github or GitHub(cache_dir=cache_dir, offline=offline)
    requested = list(dict.fromkeys(profile.slots if slots is None else slots))
    requested = [slot for slot in requested if slot in profile.slots]
    matchers = _prepare_matchers(requested, profile)
    queries = (
        [("code", q) for q in TOKEN_QUERIES]
        if any(slot.startswith("token-") for slot in requested)
        else []
    )
    queries += (
        [
            ("repos", "agent skills token optimization"),
            ("repos", "awesome-agent-skills"),
            ("repos", "rtk token compression"),
            ("repos", "repomix"),
            ("repos", "GitNexus"),
        ]
        if any(slot.startswith("token-") for slot in requested)
        else []
    )
    # Every requested slot gets a query; technology names are manifest keys, never source text.
    queries += [
        ("code", f'filename:SKILL.md "{terms_for(slot)[0]}"')
        if terms_for(slot, profile) == terms_for(slot)
        else ("code", f'filename:SKILL.md "{terms_for(slot)[0]}" "{terms_for(slot, profile)[0]}"')
        for slot in requested
        if not slot.startswith("token-")
    ]
    repositories = set(REGISTRIES)
    hints = {}

    def search(query):
        kind, text = query
        scope = (
            github.budget_scope("search", 36) if hasattr(github, "budget_scope") else nullcontext()
        )
        with scope:
            return kind, github.search(kind, text, limit=4)

    with ThreadPoolExecutor(max_workers=3) as pool:
        for kind, results in pool.map(search, queries if requested else []):
            for item in results:
                repo_data = item.get("repository", {})
                repository = (
                    item.get("fullName")
                    or item.get("full_name")
                    or repo_data.get("nameWithOwner")
                    or repo_data.get("full_name")
                )
                if not repository:
                    continue
                # Tool repositories are installed separately from their official releases.
                if kind == "repos" and not re.search(r"skill|agent", repository, re.I):
                    continue
                repositories.add(repository)
                if item.get("path", "").endswith("SKILL.md"):
                    hints.setdefault(repository, set()).add(item["path"])
    candidates, rejected = [], []
    # Reserve equal quotas for the four mandatory registries, and fetch their
    # indexes before any resources. Round-robin downloads give each registry an
    # opportunity even when an early candidate has a large bundle.
    supplemental = sorted(
        repositories - set(REGISTRIES), key=lambda repo: (repo not in hints, repo)
    )[:SUPPLEMENTAL_REPOSITORIES]
    ordered = REGISTRIES + supplemental if requested else []
    if allowed_repositories is not None:
        allowed = set(allowed_repositories)
        ordered = [repo for repo in ordered if repo in allowed]
        ordered += sorted(allowed - set(ordered))[:SUPPLEMENTAL_REPOSITORIES]
    indexed, complete = {}, set()

    def scope_for(repository):
        if not hasattr(github, "budget_scope"):
            return nullcontext()
        return (
            github.budget_scope(repository, 96 if len(requested) == 1 else 28)
            if repository in REGISTRIES
            else github.budget_scope(repository, 8)
        )

    def snapshot(repository):
        try:
            with scope_for(repository):
                meta, commit, tree = github.snapshot(repository)
            limited = None
            if len(tree) > MAX_TREE_ENTRIES:
                tree = tree[:MAX_TREE_ENTRIES]
                limited = f"repository index capped at {MAX_TREE_ENTRIES} entries"
            relevant, skill_count = [], 0
            for index, entry in enumerate(tree):
                if (
                    index % 64 == 0
                    and hasattr(github, "remaining_seconds")
                    and github.remaining_seconds() <= 0
                ):
                    limited = "repository index stopped at discovery deadline"
                    break
                path = entry.get("path", "")
                if entry.get("type") != "blob" or not (
                    path == "SKILL.md" or path.endswith("/SKILL.md")
                ):
                    continue
                if skill_count >= MAX_SKILL_PATHS:
                    limited = f"repository index capped at {MAX_SKILL_PATHS} skill paths"
                    break
                skill_count += 1
                if path in hints.get(repository, set()) or infer_slot(
                    path, "", requested, profile, matchers
                ):
                    relevant.append(path)
            relevant.sort(key=lambda path: (path not in hints.get(repository, set()), path))
            diagnostic = (
                {"repository": repository, "reason": limited, "partial": True} if limited else None
            )
            return repository, (meta, commit, tree, relevant[:12]), diagnostic
        except Exception as exc:
            reason = str(exc) if isinstance(exc, (GitHubError, ValueError)) else type(exc).__name__
            return repository, None, {"repository": repository, "reason": reason[:250]}

    # Mandatory registries are scheduled as one fair group before search hits.
    with ThreadPoolExecutor(max_workers=4) as pool:
        for group in (ordered[:4], ordered[4:]):
            for repository, index, error in pool.map(snapshot, group):
                if error:
                    rejected.append(error)
                if index is not None:
                    indexed[repository] = index
                    if not error:
                        complete.add(repository)

    for round_index in range(12):
        for repository in ordered:
            if repository not in indexed:
                continue
            meta, commit, tree, paths = indexed[repository]
            if round_index < len(paths):
                path = paths[round_index]
                try:
                    with scope_for(repository):
                        candidate = candidate_from_tree(
                            github,
                            repository,
                            meta,
                            commit,
                            tree,
                            path,
                            requested,
                            profile,
                            matchers,
                        )
                    candidates.append(candidate)
                except Exception as exc:
                    reason = (
                        str(exc)
                        if isinstance(exc, (GitHubError, ValueError))
                        else type(exc).__name__
                    )
                    rejected.append(
                        {"repository": repository, "path": path, "reason": reason[:250]}
                    )
                    if isinstance(exc, GitHubError):
                        complete.discard(repository)
                        # Cache hits might remain, but repeatedly retrying the same
                        # exhausted registry adds no useful network coverage.
                        indexed.pop(repository)
    stats = dict(getattr(github, "stats", {}))
    return candidates, {
        "queries": sorted(github.queries, key=lambda q: (q["kind"], q["query"])),
        "errors": github.errors,
        "rejected": rejected,
        "registries": ordered,
        "remote_candidates": len(candidates),
        "requested_slots": requested,
        "cache": stats,
        "degraded": bool(
            github.errors
            or any(repo not in complete for repo in ordered)
            or stats.get("budget_exhausted", 0)
        ),
        "registry_coverage": {repo: repo in complete for repo in REGISTRIES if repo in ordered},
        "limits": {
            "repositories": len(REGISTRIES) + SUPPLEMENTAL_REPOSITORIES,
            "supplemental_repositories": SUPPLEMENTAL_REPOSITORIES,
            "skills_per_repository": 12,
            "resources_per_skill": 80,
            "bytes_per_skill": 2_000_000,
            "network_requests": 180,
            "search_network_requests": 36,
            "registry_network_requests": 28,
            "supplemental_repository_network_requests": 8,
            "tree_entries_indexed": MAX_TREE_ENTRIES,
            "skill_paths_indexed": MAX_SKILL_PATHS,
            "terms_per_slot": MAX_TERMS_PER_SLOT,
            "network_deadline_seconds": 120,
        },
    }
