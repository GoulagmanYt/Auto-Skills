"""Deterministic, conservative selection: one winner per functional slot."""

import json
import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .profile import BASE_SLOTS, TECH_SLOTS, Profile


@dataclass
class Candidate:
    slot: str
    name: str
    body: str
    source: str = "github"
    repository: str = ""
    commit: str = ""
    remote_path: str = ""
    stars: int = 0
    updated: str = ""
    compatibility: dict[str, str] = field(default_factory=dict)
    files: dict[str, bytes] = field(default_factory=dict)
    score: float = 0
    license: str = ""
    executable_files: set[str] = field(default_factory=set)
    required_tools: set[str] = field(default_factory=set)
    technologies: set[str] = field(default_factory=set)
    declared_slot: bool = False
    scope: str = "."


def clean_markdown(text: str) -> str:
    """Preserve instructions, front matter, relative links and fenced examples."""
    output, fence = [], None
    for line in text.replace("\r\n", "\n").splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            if fence is None:
                fence = marker[1][0]
            elif marker[1][0] == fence:
                fence = None
        if fence is None and (
            re.match(r"^\s*\[!\[.*(?:badge|shields\.io)", line, re.I)
            or re.match(r"^\s*<!--[^>]*-->\s*$", line)
        ):
            continue
        if not fence and not line.strip() and output and not output[-1]:
            continue
        output.append(line.rstrip())
    return "\n".join(output).strip() + "\n"


def major(spec: str):
    found = re.search(r"(?<!\w)(\d+)", spec)
    return int(found[1]) if found else None


@dataclass(frozen=True)
class _Range:
    low: tuple[int, ...] = (0, 0, 0)
    high: tuple[int, ...] | None = None
    low_closed: bool = True
    high_closed: bool = False


def _intersection(left, right):
    low = max(left.low, right.low)
    low_closed = all(r.low_closed for r in (left, right) if r.low == low)
    highs = [r.high for r in (left, right) if r.high is not None]
    high = min(highs) if highs else None
    high_closed = all(r.high_closed for r in (left, right) if r.high == high)
    if high is not None and (low > high or (low == high and not (low_closed and high_closed))):
        return None
    return _Range(low, high, low_closed, high_closed)


def _ranges(spec):
    """Parse a bounded semver subset; unsupported syntax stays unverified."""
    result = []
    for alternative in str(spec).strip().split("||"):
        terms = re.findall(
            r"(>=|<=|==|~=|>|<|=|\^|~)?\s*(v?\d+(?:\.(?:\d+|[xX*])){0,2}|[xX*])", alternative
        )
        residue = re.sub(
            r"(>=|<=|==|~=|>|<|=|\^|~)?\s*(v?\d+(?:\.(?:\d+|[xX*])){0,2}|[xX*])", "", alternative
        )
        if not terms or residue.strip(" ,\t"):
            return []
        interval = _Range()
        for operator, value in terms:
            raw = value.lstrip("v").split(".")
            if raw[0] in {"x", "X", "*"}:
                if operator:
                    return []
                continue
            numeric = []
            for part in raw:
                if part in {"x", "X", "*"}:
                    break
                numeric.append(int(part))
            count = len(numeric)
            target = tuple(numeric + [0] * (3 - count))

            def increment(index, target=target):
                return target[:index] + (target[index] + 1,) + (0,) * (2 - index)

            if operator in {"", "=", "=="}:
                term = (
                    _Range(target, target, True, True)
                    if count == 3
                    else _Range(target, increment(count - 1))
                )
            elif operator == "^":
                index = next((i for i, part in enumerate(target) if part), count - 1)
                term = _Range(target, increment(index))
            elif operator in {"~", "~="}:
                index = max(0, count - 2) if operator == "~=" else min(1, count - 1)
                term = _Range(target, increment(index))
            elif operator in {">", ">="}:
                term = _Range(target, low_closed=operator == ">=")
            else:
                term = _Range(high=target, high_closed=operator == "<=")
            interval = _intersection(interval, term)
            if interval is None:
                return []
        result.append(interval)
    # Merge overlapping alternatives so containment is independent of union spelling.
    merged = []
    for current in sorted(result, key=lambda r: (r.low, not r.low_closed)):
        if merged and (
            merged[-1].high is None
            or current.low < merged[-1].high
            or (current.low == merged[-1].high and (current.low_closed or merged[-1].high_closed))
        ):
            previous = merged.pop()
            high = (
                None if None in (previous.high, current.high) else max(previous.high, current.high)
            )
            closed = any(r.high_closed for r in (previous, current) if r.high == high)
            merged.append(_Range(previous.low, high, previous.low_closed, closed))
        else:
            merged.append(current)
    return merged


def compatible(project: str, constraint: str):
    """Every possible project version must satisfy the advertised constraint."""
    projects, allowed = _ranges(project), _ranges(constraint)
    return bool(projects and allowed) and all(
        any(_intersection(version, bound) == version for bound in allowed) for version in projects
    )


def _frontmatter(body):
    match = re.match(r"\A---[ \t]*\n(.*?)\n---(?:\n|$)", body.replace("\r\n", "\n"), re.S)
    return match[1] if match else ""


def _declared_values(text, keys):
    """Read plain scalar/flow/block lists for a small, documented metadata subset."""
    text = text.rstrip() + "\n"
    result = set()
    for key in keys:
        pattern = rf"(?mi)^[ \t]*{re.escape(key)}:[ \t]*([^\n]*)(?:\n((?:[ \t]+-[^\n]*\n?)*))"
        for match in re.finditer(pattern, text):
            value = match[1].split(" #", 1)[0].strip()
            values = (
                value.strip("[]").split(",")
                if value
                else re.findall(r"(?m)^\s*-\s*(.+)$", match[2])
            )
            result.update(v.strip(" \t\"'") for v in values if v.strip(" \t\"'"))
    return result


def _tool_name(name):
    name = str(name).lower().strip().removeprefix("tools.")
    if "mcp__" in name:
        name = name.split("mcp__", 1)[1].split("__", 1)[0]
    name = re.sub(r"^(?:mcp:|exec:)", "", name)
    return name.removesuffix(".exe").replace("-mcp", "").replace("_mcp", "")


def _requirements(candidate):
    metadata = _frontmatter(candidate.body)
    for match in re.finditer(
        r"(?m)^(?:x-bootstrap-compatibility|compatibility):[ \t]*([^\n]*)\n?((?:[ \t]+[^\n]*\n?)*)",
        metadata,
    ):
        inline, nested = match.groups()
        if inline.strip().startswith("{"):
            try:
                mapping = json.loads(inline)
            except ValueError:
                mapping = {}
            if isinstance(mapping, dict):
                for tech, constraint in mapping.items():
                    if isinstance(tech, str) and isinstance(constraint, str):
                        candidate.compatibility.setdefault(tech.lower(), constraint)
        elif not inline.strip():
            for tech, constraint in re.findall(r"(?m)^\s+([\w.-]+):[ \t]*([^\n]+)", nested):
                candidate.compatibility.setdefault(tech.lower(), constraint.strip(" \t\"'"))
    tools = set(candidate.required_tools) | _declared_values(
        metadata,
        (
            "required-tools",
            "required_tools",
            "required-executables",
            "bins",
            "x-bootstrap-required-tools",
        ),
    )
    # agents/openai.yaml is declarative; allowed-tools alone is not a requirement.
    for path, data in candidate.files.items():
        if path.replace("\\", "/").endswith("agents/openai.yaml"):
            text = data.decode("utf-8", errors="replace")
            dependency = re.search(r"(?m)^dependencies:\s*\n((?:[ \t]+[^\n]*\n?)*)", text)
            if dependency:
                for item in re.split(r"(?m)^\s*-\s*", dependency[1])[1:]:
                    kind = re.search(r"(?m)^\s*type:\s*[\"']?(mcp|executable|command)\b", item)
                    value = re.search(r"(?m)^\s*(?:value|name|command):\s*[\"']?([\w.:/-]+)", item)
                    if kind and value:
                        tools.add(value[1])
    names = re.findall(r"(?mi)^name:[ \t]*([^\n]+)", metadata)
    identity = " ".join((candidate.name, candidate.remote_path, *names)).lower().replace("_", "-")
    # This known connector skill cannot perform its advertised work without Notion.
    if re.search(r"\bnotion\b", identity) or re.search(
        r"\brequires? (?:access to )?(?:the )?Notion(?: MCP| connector)\b"
        r"|\bNotion MCP (?:is )?required\b",
        candidate.body,
        re.I,
    ):
        tools.add("notion")
    if re.search(r"\btrailmark\b", candidate.body, re.I) and re.search(
        r"\b(?:requires?|uvx|uv tool|python 3\.12)\b", candidate.body, re.I
    ):
        tools.update({"uv", "trailmark"})
    technologies = set(candidate.technologies) | set(candidate.compatibility)
    technologies |= _declared_values(
        metadata,
        ("technologies", "technology", "frameworks", "languages", "x-bootstrap-technologies"),
    )
    known = set(TECH_SLOTS) | {
        "javascript",
        "typescript",
        "react-native",
        "expo",
        "python",
        "rust",
        "go",
        "ruby",
        "php",
        "java",
        "dotnet",
        "node",
        "vitest",
        "jest",
        "playwright",
        "cypress",
        "selenium",
    }
    technologies.update(
        tech for tech in known if re.search(r"(?<![\w])" + re.escape(tech) + r"(?![\w])", identity)
    )
    return {_tool_name(t) for t in tools}, {t.lower() for t in technologies}


def _version_evidence(profile, tech):
    evidence = list(getattr(profile, "resolved_versions", {}).get(tech, []))
    evidence.extend(
        source.get("constraint", source.get("version", "detected"))
        for source in getattr(profile, "technology_sources", {}).get(tech, [])
    )
    # Include all numeric declarations, even when only one workspace has a lockfile.
    numeric = [str(value) for value in evidence if re.search(r"\d", str(value))]
    return list(dict.fromkeys(numeric)) or [profile.technologies.get(tech, "detected")]


def _slot_technologies(profile, slot):
    # General functional slots use technology hints for tailoring, not eligibility.
    if slot in BASE_SLOTS or slot in {"e2e-testing", "static-analysis"}:
        return set()
    declared = getattr(profile, "slot_technologies", {}).get(slot)
    if declared:
        return set(declared)
    result = {
        tech
        for tech, target in TECH_SLOTS.items()
        if target == slot and tech in profile.technologies
    }
    if slot.startswith(("language-", "framework-", "orm-", "database-")):
        result.add(slot.split("-", 1)[1])
    return result


FORBIDDEN = [
    r"ignore (?:all |any )?(?:previous|system|developer|higher.priority) instructions",
    r"(?:reveal|print|upload|send|exfiltrate).{0,35}(?:api.keys?|credentials|auth\.json|secrets)",
    r"(?:always|must).{0,25}(?:read (?:the )?(?:whole|entire|all) (?:files|repository)|chain.of.thought)",
    r"(?:disable|bypass).{0,25}(?:sandbox|approval|security)",
    r"(?:curl|wget).{0,150}\|\s*(?:ba)?sh",
    r"(?:must|always|required).{0,50}(?:ask (?:the )?user|user approval|manual confirmation)",
    r"(?:never|do not|don't).{0,15}(?:use rtk|compress output|use local skills)",
    r"(?:npm|pip|cargo|git).{0,35}(?:install --global|install -g|push --force|reset --hard)",
]


def _token_slot_relevant(candidate):
    """Token-saving slots require their actual purpose, not ambiguous keywords."""
    if not candidate.slot.startswith("token-"):
        return True
    metadata = _frontmatter(candidate.body)
    description = re.search(r"(?m)^description:[^\n]*(?:\n[ \t]+[^\n]*)*", metadata)
    # A declared slot or skill name alone is not evidence of useful instructions.
    instructions = re.sub(r"\A---[^\n]*\n.*?\n---(?:\n|$)", "", candidate.body, flags=re.S)
    text = (instructions + "\n" + (description[0] if description else "")).lower()
    compression = bool(
        re.search(r"\b(?:compress|reduc|prun|truncat|filter|compact|summari|minimi)\w*", text)
    )
    output = bool(
        re.search(
            r"\b(?:terminal|command|cli|console|tool)[ -]+(?:output|logs?)\b|\b(?:output|log)[ -]+compression\b",
            text,
        )
    )
    model_tokens = bool(
        re.search(r"\b(?:llms?|language models?|prompts?|context windows?|model)\b", text)
        and re.search(r"\btokens?\b", text)
    )
    if candidate.slot == "token-output-compression":
        return compression and (output or model_tokens)
    if candidate.slot == "token-context-pruning":
        return bool(
            re.search(
                r"\bcontext[ -]+(?:prun\w*|budget|window)\b|\b(?:prun\w*|trim\w*|reduc\w*) (?:the )?(?:llm )?context\b|\bsurgical reads?\b|\bbounded (?:line )?reads?\b",
                text,
            )
        )
    if candidate.slot == "token-reasoning":
        return bool(re.search(r"\b(?:model_)?reasoning_effort\b", text))
    if candidate.slot == "token-prompt-cache":
        return bool(re.search(r"\bprompt[ -]+cach\w*\b|\bcach\w* (?:the )?prompt\b", text))
    if candidate.slot == "token-cli-wrapper":
        return bool(re.search(r"\b(?:rtk|repomix|gitnexus)\b", text)) or (
            bool(re.search(r"\b(?:cli|command[ -]line|terminal|wrapper)\b", text))
            and compression
            and (output or model_tokens)
        )
    return False


def rejection(candidate: Candidate, profile: Profile):
    body = candidate.body
    if candidate.slot not in profile.slots:
        return "irrelevant slot"
    if len(body) < 100 or len(body) > 18_000:
        return "vague or verbose (100..18000 characters required)"
    if candidate.source != "bundled":
        if not _token_slot_relevant(candidate):
            return "missing token-saving purpose for slot: " + candidate.slot
        # Functional slots are portable only when the skill's advertised domain is.
        # Do not turn game-frame profiling into API/database performance guidance.
        metadata = _frontmatter(body)
        description = re.search(r"(?m)^description:[^\n]*(?:\n[ \t]+[^\n]*)*", metadata)
        focus = description[0] if description else ""
        if re.search(r"\bReact Native\b|\bExpo\b.*\bmobile\b", focus, re.I) and not {
            "react-native",
            "expo",
        }.intersection(profile.technologies):
            return "technology not detected: react-native/expo mobile application"
        if (
            candidate.slot == "token-context-pruning"
            and re.search(
                r"graph.informed source slices|function/class/caller/callee|bounded source slices.*code.analysis",
                focus,
                re.I,
            )
            and not (
                {
                    "javascript",
                    "typescript",
                    "python",
                    "rust",
                    "go",
                    "ruby",
                    "php",
                    "java",
                    "dotnet",
                    "solidity",
                    "c",
                    "cpp",
                }.intersection(profile.technologies)
                or any(slot.startswith("language-") for slot in profile.slots)
            )
        ):
            return "missing source-code analysis purpose in repository"
        if re.search(
            r"\b(?:game (?:performance|development|engine)|gameplay|draw.call|frame.time budget)\b",
            focus,
            re.I,
        ):
            gaming = {
                "unity",
                "godot",
                "unreal",
                "bevy",
                "ggez",
                "macroquad",
                "phaser",
                "pixi.js",
                "babylonjs",
                "gamedev",
            }
            if not gaming.intersection(profile.technologies):
                return "missing game-development domain for game-focused skill"
        required_tools, technologies = _requirements(candidate)
        candidate.required_tools.update(required_tools)
        candidate.technologies.update(technologies)
        available = {_tool_name(tool) for tool in getattr(profile, "available_tools", [])}
        missing = required_tools - available
        if missing:
            return "missing required tool/connector: " + ", ".join(sorted(missing))
        absent = technologies - set(profile.technologies)
        if absent:
            return "technology not detected: " + ", ".join(sorted(absent))
        slot_technologies = _slot_technologies(profile, candidate.slot)
        supported = technologies | {
            tech
            for tech in slot_technologies
            if re.search(r"(?<!\w)" + re.escape(tech) + r"(?!\w)", body, re.I)
        }
        if slot_technologies and not (slot_technologies & supported):
            return "missing technology match for slot: " + ", ".join(sorted(slot_technologies))
        instructions = [body] + [
            data.decode("utf-8", errors="replace")
            for path, data in candidate.files.items()
            if path.endswith(".md")
        ]
        if "react" in profile.technologies:
            # Imports in bundled rules are API requirements even without a declared
            # compatibility range on the upstream SKILL.md.
            react_192 = any(
                re.search(
                    r"import\s*\{[^}]*\b(?:Activity|useEffectEvent)\b[^}]*\}\s*from\s*['\"]react['\"]"
                    r"|<Activity\b",
                    text,
                    re.S,
                )
                for text in instructions
            )
            if react_192 and not all(
                compatible(v, ">=19.2") for v in _version_evidence(profile, "react")
            ):
                return "unverified/incompatible React API requirement: react >=19.2"
        if any(re.search(rule, text, re.I | re.S) for text in instructions for rule in FORBIDDEN):
            return "contradicts local token/security/autonomy policy"
        if not re.search(r"(?mi)^description:\s*\S", body):
            return "missing skill description"
        if candidate.updated:
            try:
                age = datetime.now(UTC) - datetime.fromisoformat(
                    candidate.updated.replace("Z", "+00:00")
                )
                if age.days > 1095:
                    return "repository inactive for more than three years"
            except ValueError:
                return "invalid provenance timestamp"
        # A technology skill explicitly targeting another major is not silently accepted.
        for tech in technologies | slot_technologies:
            if tech not in candidate.compatibility:
                advertised = re.findall(r"\b" + re.escape(tech) + r"\s+(\d+)\b", body, re.I)
                if tech == "rust":
                    advertised = [
                        v for v in advertised if v not in {"2015", "2018", "2021", "2024"}
                    ]
                if advertised:
                    constraint = " || ".join(sorted(set(advertised)))
                    if not all(
                        compatible(version, constraint)
                        for version in _version_evidence(profile, tech)
                    ):
                        return f"unverified/incompatible {tech} major"
    for tech, constraint in candidate.compatibility.items():
        if tech not in profile.technologies or not all(
            compatible(version, constraint) for version in _version_evidence(profile, tech)
        ):
            return f"unverified/incompatible version: {tech} {constraint}"
    return None


def _ranking(candidate):
    return (
        candidate.score,
        candidate.repository,
        candidate.name,
        candidate.remote_path,
        candidate.commit,
        candidate.body,
        tuple(sorted(candidate.files.items())),
        candidate.source,
    )


def select(candidates: list[Candidate], profile: Profile):
    winners, rejected = {}, []
    for candidate in candidates:
        reason = rejection(candidate, profile)
        if reason:
            rejected.append(
                {
                    "name": candidate.name,
                    "slot": candidate.slot,
                    "repository": candidate.repository,
                    "reason": reason,
                }
            )
            continue
        words = re.findall(r"\b\w+\b", candidate.body.lower())
        diversity = len(set(words)) / max(len(words), 1)
        actions = len(
            re.findall(
                r"\b(?:run|check|test|verify|use|avoid|measure|read|validate)\b",
                candidate.body,
                re.I,
            )
        )
        # Relevance dominates quality; popularity only distinguishes close peers.
        relevant = len(candidate.technologies & profile.technologies.keys())
        candidate.score = round(
            min(relevant, 5) * 100
            + 20 * diversity
            + min(actions, 18)
            + min(math.log2(max(0, candidate.stars) + 1), 3)
            - len(candidate.body) / 1200
            + (3 if candidate.source == "bundled" else 6),
            4,
        )
        previous = winners.get(candidate.slot)
        if previous is None or _ranking(candidate) > _ranking(previous):
            if previous:
                rejected.append(
                    {"name": previous.name, "slot": previous.slot, "reason": "lower slot score"}
                )
            winners[candidate.slot] = candidate
        else:
            rejected.append(
                {"name": candidate.name, "slot": candidate.slot, "reason": "lower slot score"}
            )
    return [winners[s] for s in profile.slots if s in winners], rejected
