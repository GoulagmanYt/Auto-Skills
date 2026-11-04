"""Read-only repository matrix: offline regression gate and bounded real GitHub discovery."""
# ruff: noqa: E402

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "src"))
sys.path.insert(0, str(WORKSPACE))

from codex_bootstrap.fs import json_text
from codex_bootstrap.github import GitHub
from codex_bootstrap.profile import BASE_SLOTS
from codex_bootstrap.proposal import propose
from codex_bootstrap.token_tools import install_token_tools
from tools.repo_scenarios import SCENARIOS

# Independent expectations for the language/build/test implications of the handwritten fixtures.
EXTRA_EXPECTED = {
    "next-commerce": {"language-javascript", "static-analysis"},
    "vue-dashboard": {"language-javascript", "static-analysis"},
    "desktop-midi": {
        "language-javascript",
        "language-typescript",
        "static-analysis",
        "build-vite",
        "test-vitest",
        "audio-cpal",
    },
    "mixed-monorepo": {"language-javascript", "static-analysis", "test-vitest"},
    "solidity-project": {"language-javascript", "static-analysis"},
}

# These fixture manifests declare client bindings, not a database server version.
UNKNOWN_ENGINE_VERSIONS = {
    "go-gin-service": {"postgres"},
    "rust-web-service": {"sqlite"},
    "driver-only-node": {"postgres", "redis"},
    "driver-only-python": {"postgres", "redis"},
    "driver-only-sqlite": {"sqlite"},
    "aspnet-api": {"sqlserver"},
}
ENGINE_VERSIONS = {
    "next-commerce": {"postgres": "16"},
    "fastapi-api": {"postgres": "16"},
    "django-service": {"postgres": "16", "redis": "7"},
}


def classified_skills(entries):
    internal, external = [], []
    for entry in entries:
        value = dict(entry)
        value["scope"] = entry.get("scope", ".")
        if entry["source"] == "github":
            if entry.get("repository", "").startswith("simulation/"):
                raise ValueError(
                    "synthetic registry must never be presented as real external discovery"
                )
            value["pinned"] = len(entry.get("commit", "")) == 40 and bool(entry.get("url"))
            value["quality_scope"] = "heuristic"
            value["quality_checks"] = {
                "commit_pinned": value["pinned"],
                "license_declared": entry.get("license", "") not in {"", "NOASSERTION"},
                "compatibility_declared": bool(entry.get("compatibility")),
                "technology_hints": entry.get("technologies", []),
                "required_tools": entry.get("required_tools", []),
                "resource_count": entry.get("resource_count", 0),
            }
            external.append(value)
        elif entry["source"] == "bundled":
            internal.append(value)
        else:
            raise ValueError("unclassified skill source")
    return internal, external


def regression_failures(results, checks):
    fields = (
        "unexpected_slots",
        "unexpected_missing_slots",
        "ambiguous_versions",
        "version_role_gaps",
        "scope_gaps",
        "duplicate_skill_keys",
        "external_provenance_gaps",
    )
    failures = [
        r["repository"] for r in results if not r["read_only"] or any(r.get(key) for key in fields)
    ]
    return failures + [c["name"] for c in checks if not c["passed"] or not c["read_only"]]


def create_repository(root, files):
    root.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    for relative, value in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")


def snapshot(root):
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


def assess_scenario(spec, root, *, live=False, github=None):
    create_repository(root, spec.files)
    before = snapshot(root)
    original_open = Path.open

    def guarded_open(path, *args, **kwargs):
        if path == root / "src/never-read.tsx":
            raise AssertionError("The profiler read an implementation file")
        return original_open(path, *args, **kwargs)

    errors_before = len(github.errors) if live and github is not None else 0
    with patch.object(Path, "open", guarded_open):
        report = propose(root, offline=not live, github=github)
    new_discovery_errors = (
        list(github.errors[errors_before:])
        if live and github is not None
        else list(report["discovery"].get("errors", []))
    )
    report["matrix_discovery_diagnostics"] = {
        "scope": "new errors recorded during this scenario; shared client history excluded",
        "errors": new_discovery_errors,
    }
    after = snapshot(root)
    actual = {entry["slot"] for entry in report["selected"]}
    required = set(spec.required) | EXTRA_EXPECTED.get(spec.slug, set())
    missing = sorted(required - actual)
    unexpected_missing = sorted(set(missing) - set(spec.known_gaps))
    unexpected = sorted((actual - set(BASE_SLOTS) - required) | (actual & set(spec.forbidden)))
    ambiguous = sorted(
        key
        for key, version in report["profile"]["technologies"].items()
        if version == "multiple" and key not in spec.allowed_multiple
    )
    version_roles = sorted(
        key
        for key in UNKNOWN_ENGINE_VERSIONS.get(spec.slug, set())
        if report["profile"]["technologies"].get(key) not in {None, "detected", "unresolved"}
    )
    for engine, version in ENGINE_VERSIONS.get(spec.slug, {}).items():
        if report["profile"]["technologies"].get(engine) != version:
            version_roles.append(engine)
    keys = [f"{entry.get('scope', '.')}::{entry['slot']}" for entry in report["selected"]]
    duplicates = sorted(key for key, count in Counter(keys).items() if count > 1)
    scope_gaps = []
    if spec.slug == "mixed-monorepo":
        for scope in ("apps/legacy", "apps/web"):
            if not any(
                e["slot"] == "framework-react" and e.get("scope") == scope
                for e in report["selected"]
            ):
                scope_gaps.append(scope + "::framework-react")
        for scope, expected in (("apps/legacy", "^18.3.0"), ("apps/web", "^19.0.0")):
            technologies = report.get("workspaces", {}).get(scope, {}).get("technologies", {})
            if technologies.get("react") != expected:
                scope_gaps.append(scope + "::react-version")
        if "react" in report.get("workspaces", {}).get("services/api", {}).get("technologies", {}):
            scope_gaps.append("services/api::unexpected-react")
    internal, external = classified_skills(report["selected"])
    verdict = "Partiel" if missing or ambiguous or version_roles or scope_gaps else "Coh\u00e9rent"
    if spec.slug == "documentation-only":
        if any(e["slot"] in {"build", "unit-testing", "performance"} for e in report["selected"]):
            unexpected.append("documentation-baseline-not-adapted")
        plan = report.get("tool_plan", [])
        tool_names = {t if isinstance(t, str) else t["name"] for t in plan}
        if tool_names & {"rtk", "repomix"}:
            unexpected.append("documentation-tools-not-adapted")
    if unexpected or unexpected_missing or before != after or duplicates:
        verdict = "Incoherent"
    result = {
        "repository": spec.slug,
        "title": spec.title,
        "verdict": verdict,
        "skills": [entry["name"] for entry in report["selected"]],
        "skill_keys": keys,
        "duplicate_skill_keys": duplicates,
        "scope_gaps": scope_gaps,
        "internal_skills": internal,
        "external_skills": external,
        "external_specialty_gaps": sorted(
            slot
            for slot in required - set(BASE_SLOTS)
            if not any(e["slot"] == slot for e in external)
        ),
        "external_provenance_gaps": [
            e["name"]
            for e in external
            if not e["pinned"] or not e.get("reason") or not e.get("license")
        ],
        "external_discovery": "real-github-live-or-public-cache" if live else "not-run-offline",
        "tool_plan": report.get("tool_plan", []),
        "known_gaps": sorted(spec.known_gaps),
        "discovery_errors": len(new_discovery_errors),
        "discovery_errors_scope": "new errors recorded during this scenario",
        "specific_skills": [
            entry["name"] for entry in report["selected"] if entry["slot"] not in BASE_SLOTS
        ],
        "missing_slots": missing,
        "unexpected_slots": unexpected,
        "unexpected_missing_slots": unexpected_missing,
        "ambiguous_versions": ambiguous,
        "version_role_gaps": version_roles,
        "read_only": before == after,
        "note": spec.note,
        "manifest_count": len(report["profile"]["manifests"]),
    }
    return result, report


class SyntheticRegistry:
    """Duck-typed GitHub client, exercising discover()/candidate_from_tree()/select()."""

    repository = "simulation/skills"

    def __init__(self, skills, unavailable=False):
        self.skills = skills
        self.queries, self.errors = [], []
        self.snapshots = 0
        self.unavailable = unavailable
        self.paths = {
            f"skills/{name}/SKILL.md": content.encode() for name, content in skills.items()
        }

    def search(self, kind, query, limit=4):
        self.queries.append({"kind": kind, "query": query})
        if self.unavailable:
            if not self.errors:
                self.errors.append(
                    {"operation": "synthetic-registry", "reason": "simulated outage"}
                )
            return []
        if kind == "repos":
            return [{"fullName": self.repository}]
        return [
            {"repository": {"nameWithOwner": self.repository}, "path": path}
            for path in list(self.paths)[:limit]
        ]

    def snapshot(self, repository):
        self.snapshots += 1
        if self.unavailable:
            raise RuntimeError("synthetic registry outage")
        tree = (
            []
            if repository != self.repository
            else [
                {"path": path, "type": "blob", "mode": "100644", "sha": path, "size": len(content)}
                for path, content in self.paths.items()
            ]
        )
        return (
            {"private": False, "license": {"spdx_id": "MIT"}, "stargazers_count": 1_000_000},
            "a" * 40,
            tree,
        )

    def blob(self, repository, sha, max_size=256000):
        return self.paths[sha]


def registry_skill(
    name,
    slot,
    *,
    compatibility=None,
    technologies=None,
    tools=None,
    body=None,
    description="Use this workflow for the declared repository action.",
):
    text = f"---\nname: {name}\ndescription: {description}\nx-bootstrap-slot: {slot}\n"
    if compatibility:
        text += "x-bootstrap-compatibility: " + json.dumps(compatibility) + "\n"
    if technologies:
        text += "x-bootstrap-technologies: " + json.dumps(technologies) + "\n"
    if tools:
        text += "required-tools: " + json.dumps(tools) + "\n"
    return (
        text
        + "---\n\n"
        + (
            body
            or "Check the manifest and public API before editing. Read bounded relevant code ranges. Run existing checks and verify the observable behavior, including validation and failure cases.\n"
        )
    )


def adversarial_checks(base):
    cases = []

    def check(name, files, skills, predicate, *, unavailable=False):
        root = base / name
        create_repository(root, files)
        before = snapshot(root)
        registry = SyntheticRegistry(skills, unavailable=unavailable)
        report = propose(root, github=registry)
        selected = {entry["name"] for entry in report["selected"]}
        reasons = [
            entry.get("reason", "")
            for entry in report["selection_rejections"] + report["discovery"].get("rejected", [])
        ]
        result = {
            "name": name,
            "passed": bool(predicate(selected, reasons, report)),
            "read_only": before == snapshot(root),
            "registry_snapshots": registry.snapshots,
            "selected_fixture_skills": sorted(selected & set(skills)),
            "rejection_reasons": reasons,
            "synthetic_registry": True,
        }
        cases.append(result)

    react = {"package.json": '{"dependencies":{"react":"^19.0.0"}}'}
    check(
        "react-version",
        react,
        {
            "fixture-react19": registry_skill(
                "fixture-react19", "framework-react", compatibility={"react": ">=19,<20"}
            ),
            "fixture-react18": registry_skill(
                "fixture-react18", "framework-react", compatibility={"react": ">=18,<19"}
            ),
        },
        lambda names, reasons, report: (
            "fixture-react19" in names
            and "fixture-react18" not in names
            and any("incompatible" in r for r in reasons)
        ),
    )
    check(
        "notion-out-of-scope",
        react,
        {
            "notion-research-documentation": registry_skill(
                "notion-research-documentation", "documentation"
            ),
        },
        lambda names, reasons, report: (
            "notion-research-documentation" not in names and any("notion" in r for r in reasons)
        ),
    )
    check(
        "blockchain-is-not-token-saving",
        react,
        {
            "token-integration-analyzer": registry_skill(
                "token-integration-analyzer",
                "token-output-compression",
                body="Analyze ERC20 and ERC721 token integrations. Verify balances, allowances and token supply. "
                * 3,
            ),
        },
        lambda names, reasons, report: (
            "token-integration-analyzer" not in names and any("token-saving" in r for r in reasons)
        ),
    )
    check(
        "vue-rejects-react-skill",
        {"package.json": '{"dependencies":{"vue":"^3.5.0"}}'},
        {
            "fixture-react-ui": registry_skill(
                "fixture-react-ui", "framework-vue", technologies=["react"]
            ),
        },
        lambda names, reasons, report: (
            "fixture-react-ui" not in names and any("react" in r for r in reasons)
        ),
    )
    check(
        "orm-mismatch",
        {
            "pyproject.toml": '[project]\nname="api"\ndependencies=["fastapi>=0.115", "sqlalchemy>=2,<3"]\n'
        },
        {
            "fixture-prisma-guide": registry_skill(
                "fixture-prisma-guide", "orm-sqlalchemy", technologies=["prisma"]
            ),
        },
        lambda names, reasons, report: (
            "fixture-prisma-guide" not in names and any("prisma" in r for r in reasons)
        ),
    )
    check(
        "monorepo-workspace-specific-versions",
        {
            "apps/old/package.json": '{"dependencies":{"react":"^18.3.0"}}',
            "apps/new/package.json": '{"dependencies":{"react":"^19.0.0"}}',
        },
        {
            "fixture-react-multiversion": registry_skill(
                "fixture-react-multiversion", "framework-react", compatibility={"react": ">=18,<19"}
            ),
            "fixture-react19-only": registry_skill(
                "fixture-react19-only", "framework-react", compatibility={"react": ">=19,<20"}
            ),
        },
        lambda names, reasons, report: (
            any(
                e["name"] == "fixture-react-multiversion" and e.get("scope") == "apps/old"
                for e in report["selected"]
            )
            and any(
                e["name"] == "fixture-react19-only" and e.get("scope") == "apps/new"
                for e in report["selected"]
            )
            and not any(
                e["name"] == "fixture-react19-only" and e.get("scope") == "apps/old"
                for e in report["selected"]
            )
        ),
    )
    check(
        "missing-executable",
        react,
        {
            "fixture-ci-guide": registry_skill(
                "fixture-ci-guide", "ci-cd", tools=["auto-skills-imaginary-cli"]
            ),
        },
        lambda names, reasons, report: (
            "fixture-ci-guide" not in names
            and any("auto-skills-imaginary-cli" in r for r in reasons)
        ),
    )
    check(
        "audit-context-is-not-pruning",
        react,
        {
            "audit-context-building": registry_skill(
                "audit-context-building",
                "token-context-pruning",
                body="Build deep context for a security audit. Read functions and document their assumptions and invariants. "
                * 3,
            ),
        },
        lambda names, reasons, report: (
            "audit-context-building" not in names and any("token-saving" in r for r in reasons)
        ),
    )
    check(
        "game-performance-is-not-api-performance",
        {"pyproject.toml": '[project]\nname="api"\ndependencies=["fastapi>=0.115"]\n'},
        {
            "fixture-game-performance": registry_skill(
                "fixture-game-performance",
                "performance",
                description="Find and fix game performance problems with engine profiling and frame-time budgets.",
                body="Find and fix game performance problems. Measure frame-time budget with the engine profiler. "
                "Use Godot, Unity or Unreal profiler for draw calls, GPU bottlenecks and object pooling. "
                * 3,
            )
        },
        lambda names, reasons, report: (
            "fixture-game-performance" not in names
            and any("game" in r.lower() or "domain" in r.lower() for r in reasons)
        ),
    )
    check(
        "documentation-rejects-code-only-context",
        {"README.md": "# Documentation\nNo code manifests.\n"},
        {
            "fixture-code-context": registry_skill(
                "fixture-code-context",
                "token-context-pruning",
                description="Selects bounded source slices for function, class, caller and callee code analysis.",
                body="Prune context by selecting surgical source slices. Read partial code ranges and regex anchors. "
                "Delegate focused code analysis and verify source references in the smaller context. "
                * 3,
            )
        },
        lambda names, reasons, report: (
            "fixture-code-context" not in names
            and any(
                "code" in r.lower() or "purpose" in r.lower() or "domain" in r.lower()
                for r in reasons
            )
        ),
    )
    for version in ("18.3.0", "19.0.0", "19.2.0"):
        expected = version == "19.2.0"
        check(
            "react-modern-api-" + version.replace(".", "-"),
            {"package.json": json.dumps({"dependencies": {"react": "^" + version}})},
            {
                "fixture-react-modern-apis": registry_skill(
                    "fixture-react-modern-apis",
                    "framework-react",
                    technologies=["react"],
                    description="Use React Activity and useEffectEvent for modern UI lifecycle management.",
                    body="Verify React compatibility before editing UI lifecycle behavior. Read only relevant component code. "
                    "Use the modern APIs below and test observable effects and hidden-view state.\n"
                    "```tsx\nimport { Activity, useEffectEvent } from 'react';\n```\n",
                )
            },
            lambda names, reasons, report, expected=expected: (
                ("fixture-react-modern-apis" in names) == expected
                and (
                    expected
                    or any("19.2" in r or "incompatible" in r or "API" in r for r in reasons)
                )
            ),
        )
    check(
        "react-native-is-not-react-web",
        {"package.json": json.dumps({"dependencies": {"react": "^19.2.0", "next": "^15.2.0"}})},
        {
            "fixture-mobile-react": registry_skill(
                "fixture-mobile-react",
                "framework-react",
                technologies=["react"],
                description="React Native and Expo best practices for building performant mobile apps.",
                body="Use React Native components, Expo native modules and mobile platform APIs. "
                "Check list rendering with FlashList and test Reanimated gestures. "
                "Verify native navigation, images, fonts and mobile memory performance. " * 2,
            )
        },
        lambda names, reasons, report: (
            "fixture-mobile-react" not in names
            and any("native" in r.lower() or "expo" in r.lower() for r in reasons)
        ),
    )
    check(
        "registry-outage",
        react,
        {},
        lambda names, reasons, report: (
            report["degraded"] and all(e["source"] == "bundled" for e in report["selected"])
        ),
        unavailable=True,
    )
    return cases


def tool_inventory(root):
    root.mkdir(parents=True, exist_ok=True)
    return install_token_tools(root, offline=True)


def skill_label(entry, *, external=False):
    scope = entry.get("scope", ".")
    label = f"`{entry['name']}`" + (f" ({scope})" if scope != "." else "")
    if external:
        label += f" — [{entry['repository']}]({entry.get('url', '')})"
    return label


def matrix_markdown(results, checks, tools=None):
    live = any(r["external_discovery"] != "not-run-offline" for r in results)
    lines = [
        "# Simulations de dépôts Auto-Skills",
        "",
        "Dépôts fictifs, profilage et sélection réels, aucune installation dans les dépôts simulés.",
        (
            "Recherche GitHub réelle et cache public, bornés par un budget partagé. Les erreurs de recherche et les slots sans gagnant externe sont visibles."
            if live
            else "Mode hors ligne : catalogue intégré uniquement. La colonne extérieure vide ne mesure pas la couverture GitHub."
        ),
        "Les registres synthétiques servent uniquement aux tests adversariaux séparés ci-dessous.",
        "",
        "| Dépôt simulé | Skills intérieurs (intégrés) | Skills extérieurs (GitHub) | Plugins/outils proposés | Cohérence |",
        "|---|---|---|---|---|",
    ]
    for result in results:
        internal = ", ".join(skill_label(e) for e in result["internal_skills"]) or "Aucun"
        external = ", ".join(skill_label(e, external=True) for e in result["external_skills"])
        external = external or (
            "Aucun gagnant externe éligible" if live else "Non recherchés (hors ligne)"
        )
        plan = result.get("tool_plan", [])
        names = (
            ", ".join(f"`{t if isinstance(t, str) else t['name']}`" for t in plan)
            or "Non renseigné"
        )
        lines.append(
            f"| {result['title']} | {internal} | {external} | {names} | {result['verdict']} |"
        )
    lines += [
        "",
        "## Qualité et pertinence des skills extérieurs",
        "",
        "Ces contrôles sont des heuristiques de sélection, pas une certification de qualité : compatibilité déclarée, technologies détectées, dépendances disponibles, concision, provenance et score. Le commit fixe la version examinée.",
        "",
        "| Dépôt / workspace | Skill extérieur | Source épinglée | Compatibilité / technologies | Motif / score |",
        "|---|---|---|---|---|",
    ]
    external_count = 0
    for result in results:
        for entry in result["external_skills"]:
            external_count += 1
            constraints = json.dumps(entry.get("compatibility", {}), ensure_ascii=False)
            technologies = ", ".join(entry.get("technologies", [])) or "generic"
            reason = entry.get("reason", "").replace("|", "/").replace("\n", " ")
            lines.append(
                f"| {result['repository']} / {entry.get('scope', '.')} | `{entry['name']}` | [{entry['repository']}@{entry.get('commit', '')[:12]}]({entry.get('url', '')}) ; licence `{entry.get('license', 'unknown')}` | `{constraints}` ; {technologies} | {reason} ; {entry.get('score', '')} |"
            )
    if not external_count:
        lines.append("| — | Aucun résultat externe vérifié pendant cette exécution | — | — | — |")
    lines += ["", "## Lacunes et diagnostics", ""]
    for result in results:
        details = []
        for key, title in (
            ("missing_slots", "slots manquants"),
            ("ambiguous_versions", "versions ambiguës"),
            ("version_role_gaps", "confusions pilote/serveur"),
            ("scope_gaps", "scopes manquants"),
            ("unexpected_slots", "slots inattendus"),
        ):
            if result[key]:
                details.append(title + " : " + ", ".join(result[key]))
        if live:
            details.append(
                f"{len(result['external_skills'])} externe(s), {result['discovery_errors']} nouvelle(s) erreur(s) de recherche pendant ce scénario"
            )
            if result.get("external_specialty_gaps"):
                details.append(
                    "couverture externe absente pour : "
                    + ", ".join(result["external_specialty_gaps"])
                )
        if result["note"]:
            details.append(result["note"])
        if details:
            lines.append("- **" + result["title"] + "** : " + "; ".join(details))
    lines += [
        "",
        "## Registre synthétique : cas adversariaux (aucune recommandation externe)",
        "",
        "| Cas | Vérification |",
        "|---|---|",
    ]
    lines.extend(
        f"| `{c['name']}` | {'OK' if c['passed'] and c['read_only'] else 'ECHEC'} |" for c in checks
    )
    lines += [
        "",
        "## Critères CI",
        "",
        "La CI bloque toute nouvelle absence de slot attendu, slot incohérent, confusion pilote/serveur, ambiguïté non autorisée, duplication par workspace ou modification d’un dépôt simulé. Les lacunes autorisées sont suivies par scénario dans les entrées JSON ; elles sont actuellement vides pour les stacks annoncées.",
        "Le contrôle GitHub en direct est séparé des tests déterministes : une indisponibilité réseau ne valide ni n’invalide la qualité d’un skill absent.",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=WORKSPACE / "reports/simulations")
    parser.add_argument(
        "--live", action="store_true", help="Real GitHub discovery, shared bounded public cache"
    )
    parser.add_argument("--max-requests", type=int, default=180)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--only", action="append", choices=[s.slug for s in SCENARIOS])
    args = parser.parse_args(argv)
    if args.max_requests < 0 or not 1 <= args.timeout <= 600:
        parser.error("budget must be nonnegative and timeout must be 1..600 seconds")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    github = (
        GitHub(cache_dir=args.cache_dir, max_requests=args.max_requests, timeout=args.timeout)
        if args.live
        else None
    )
    results = []
    with tempfile.TemporaryDirectory(prefix="auto-skills-simulations-") as directory:
        root = Path(directory)
        for spec in SCENARIOS:
            if args.only and spec.slug not in args.only:
                continue
            result, report = assess_scenario(spec, root / spec.slug, live=args.live, github=github)
            results.append(result)
            path = output / spec.slug
            path.mkdir(exist_ok=True)
            (path / "proposal.json").write_text(json_text(report), encoding="utf-8")
            (path / "inputs.json").write_text(json_text(spec.files), encoding="utf-8")
        checks = adversarial_checks(root / "adversarial")
    failures = regression_failures(results, checks)
    payload = {
        "mode": "real-github-and-synthetic-adversarial-tests"
        if args.live
        else "deterministic-offline-and-synthetic-registry",
        "created_at": datetime.now(UTC).isoformat(),
        "repositories": results,
        "adversarial_checks": checks,
        "regressions": failures,
        "known_gaps": {r["repository"]: r["known_gaps"] for r in results},
        "github_budget": {
            "max_requests": args.max_requests,
            "timeout": args.timeout,
            "stats": github.stats if github else {},
            "errors": github.errors if github else [],
        },
    }
    (output / "matrix.json").write_text(json_text(payload), encoding="utf-8")
    (output / "matrix.md").write_text(matrix_markdown(results, checks), encoding="utf-8")
    print(
        f"Repositories: {len(results)}; adversarial checks: {len(checks)}; failures: {len(failures)}"
    )
    print("Report: " + str(output / "matrix.md"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
