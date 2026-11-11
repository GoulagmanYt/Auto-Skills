"""Verify pinned, licensed upstream manifest extracts; never run upstream projects.

The default is fully offline. --refresh explicitly resolves fresh public GitHub
commits and copies only each configured manifest and its upstream license.
These extracts are parser/selection evidence, not full-repository certification.
"""
# ruff: noqa: E402

import argparse
import base64
import hashlib
import json
import re
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

WORKSPACE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKSPACE / "src"))
sys.path.insert(0, str(WORKSPACE))

from codex_bootstrap.proposal import propose

FIXTURES = WORKSPACE / "fixtures" / "real-repositories"
LIMITATION = (
    "Pinned upstream manifest extracts only: tests reconstruct the copied manifest paths, "
    "not entire upstream repositories. No upstream source, build, dependency installation, "
    "or external skill discovery is executed; results do not certify whole-repository behavior."
)
PERMISSIVE = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC", "Unlicense"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def safe_relative(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or "\\" in value or ":" in value:
        raise ValueError("unsafe relative path")
    return path


def load_catalog(fixtures=FIXTURES):
    return json.loads((fixtures / "catalog.json").read_text(encoding="utf-8"))


def verify_snapshot(spec, fixtures=FIXTURES):
    """Check local bytes and immutable identities without making network requests."""
    errors = []
    try:
        slug = spec["slug"]
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
            raise ValueError("invalid slug")
        repo = spec["repository"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise ValueError("invalid public GitHub identity")
        commit = spec["commit"]
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("commit must be a full immutable Git SHA")
        original = safe_relative(spec["original_path"]).as_posix()
        folder = fixtures / slug
        provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
        for field in ("repository", "commit", "original_path", "license_spdx"):
            if provenance.get(field) != spec.get(field):
                errors.append(f"catalog/provenance mismatch: {field}")
        if provenance.get("license_spdx") not in PERMISSIVE:
            errors.append("upstream license is not an allowed permissive SPDX identifier")
        if provenance.get("github_reported_license_spdx") != provenance.get("license_spdx"):
            review = provenance.get("license_review") or {}
            if (
                review != spec.get("license_review")
                or review.get("spdx") != provenance.get("license_spdx")
                or review.get("license_sha256") != provenance.get("license_sha256")
                or not review.get("basis")
            ):
                errors.append("license review does not match copied upstream notice")
        expected_url = f"https://github.com/{repo}/blob/{commit}/{original}"
        if provenance.get("manifest_url") != expected_url:
            errors.append("manifest URL does not match pinned identity")
        license_path = safe_relative(provenance["license_original_path"]).as_posix()
        if (
            provenance.get("license_url")
            != f"https://github.com/{repo}/blob/{commit}/{license_path}"
        ):
            errors.append("license URL does not match pinned identity")
        for filename, hash_key in (
            ("manifest.txt", "manifest_sha256"),
            ("LICENSE.txt", "license_sha256"),
        ):
            body = (folder / filename).read_bytes()
            if not body:
                errors.append(f"empty copied file: {filename}")
            if digest(body) != provenance.get(hash_key) or digest(body) != spec.get(hash_key):
                errors.append(f"SHA-256 mismatch: {filename}")
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append(f"invalid snapshot: {type(error).__name__}: {error}")
    return errors


class PublicGitHub:
    """Bounded, unauthenticated reads of public GitHub metadata and pinned contents."""

    def __init__(self, *, max_requests=60, deadline_seconds=240):
        self.requests = 0
        self.max_requests = max_requests
        self.deadline = time.monotonic() + deadline_seconds

    def read(self, url):
        remaining = self.deadline - time.monotonic()
        if self.requests >= self.max_requests or remaining <= 0:
            raise RuntimeError("bounded refresh request/deadline budget exhausted")
        self.requests += 1
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Auto-Skills-manifest-verifier",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(request, timeout=min(15, remaining)) as response:
            body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError("upstream file exceeds refresh size bound")
        return body

    def json(self, path):
        return json.loads(self.read("https://api.github.com/" + path))


def refresh(fixtures=FIXTURES, *, client=None):
    """Refresh all entries, retaining failures explicitly; verification remains offline."""
    catalog = load_catalog(fixtures)
    client = client or PublicGitHub()
    failures = []
    for spec in catalog["repositories"]:
        try:
            repo = spec["repository"]
            # HEAD is resolved once during explicit refresh only. Every content read uses its SHA.
            commit = client.json(f"repos/{repo}/commits/HEAD")["sha"]
            if not re.fullmatch(r"[0-9a-f]{40}", commit):
                raise ValueError("GitHub did not return a full commit SHA")
            license_data = client.json(f"repos/{repo}/license?ref={commit}")
            reported_spdx = license_data["license"]["spdx_id"]
            license_body = base64.b64decode(license_data["content"])
            spdx = reported_spdx
            review = spec.get("license_review", {})
            if (
                spdx not in PERMISSIVE
                and review.get("license_sha256") == digest(license_body)
                and review.get("basis")
            ):
                spdx = review.get("spdx", spdx)
            if spdx not in PERMISSIVE:
                raise ValueError(f"license requires review: {spdx}")
            original = safe_relative(spec["original_path"]).as_posix()
            license_path = safe_relative(license_data["path"]).as_posix()
            manifest = client.read(
                f"https://raw.githubusercontent.com/{repo}/{commit}/{urllib.parse.quote(original, safe='/')}"
            )
            provenance = {
                "repository": repo,
                "commit": commit,
                "original_path": original,
                "manifest_url": f"https://github.com/{repo}/blob/{commit}/{original}",
                "manifest_sha256": digest(manifest),
                "license_spdx": spdx,
                "github_reported_license_spdx": reported_spdx,
                "license_review": review if spdx != reported_spdx else None,
                "license_original_path": license_path,
                "license_url": f"https://github.com/{repo}/blob/{commit}/{license_path}",
                "license_sha256": digest(license_body),
                "metadata_source": f"https://api.github.com/repos/{repo}/license?ref={commit}",
            }
            folder = fixtures / spec["slug"]
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "manifest.txt").write_bytes(manifest)
            (folder / "LICENSE.txt").write_bytes(license_body)
            write_json(folder / "provenance.json", provenance)
            for field in ("commit", "license_spdx", "manifest_sha256", "license_sha256"):
                spec[field] = provenance[field]
        except (OSError, ValueError, KeyError, RuntimeError) as error:
            failures.append(
                {"repository": spec["repository"], "reason": f"{type(error).__name__}: {error}"}
            )
    catalog["refresh_failures"] = failures
    write_json(fixtures / "catalog.json", catalog)
    return failures


def tree_hashes(root):
    return {
        path.relative_to(root).as_posix(): digest(path.read_bytes())
        for path in root.rglob("*")
        if path.is_file()
    }


def assess_repositories(fixtures=FIXTURES):
    catalog = load_catalog(fixtures)
    results = []
    valid = []
    for spec in catalog["repositories"]:
        errors = verify_snapshot(spec, fixtures)
        result = {
            "repository": spec["repository"],
            "slug": spec["slug"],
            "commit": spec.get("commit", ""),
            "original_path": spec["original_path"],
            "license_spdx": spec.get("license_spdx", ""),
            "integrity_errors": errors,
            "failures": list(errors),
        }
        results.append(result)
        if not errors:
            valid.append((spec, result))
    with tempfile.TemporaryDirectory(prefix="auto-skills-real-manifests-") as temporary:
        root = Path(temporary) / "repositories"
        root.mkdir()
        for spec, _ in valid:
            target = root / spec["slug"] / spec["original_path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((fixtures / spec["slug"] / "manifest.txt").read_bytes())
        before = tree_hashes(root)
        report = propose(
            root, offline=True, cache_dir=Path(temporary) / "offline-cache", local_paths=[]
        )
        read_only = before == tree_hashes(root) and not report["installed"]
        profiles = report["workspaces"]
        selected = report["selected"]
        for spec, result in valid:
            scope = (
                PurePosixPath(spec["slug"]) / PurePosixPath(spec["original_path"]).parent
            ).as_posix()
            profile = profiles.get(scope, {})
            technologies = profile.get("technologies", {})
            own_selected = [entry for entry in selected if entry.get("scope", ".") == scope]
            actual_slots = {entry["slot"] for entry in own_selected}
            missing_technologies = sorted(set(spec["expected_technologies"]) - set(technologies))
            missing_slots = sorted(set(spec["expected_slots"]) - actual_slots)
            language_slots = set(catalog["language_slots"])
            allowed_languages = set(spec["expected_language_slots"])
            language_spill = sorted((actual_slots & language_slots) - allowed_languages)
            technology_spill = sorted(
                (set(technologies) & set(catalog["isolation_technologies"]))
                - set(spec["expected_technologies"])
            )
            failures = result["failures"]
            failures.extend("missing technology: " + value for value in missing_technologies)
            failures.extend("missing selected slot: " + value for value in missing_slots)
            failures.extend("cross-workspace language spill: " + value for value in language_spill)
            failures.extend(
                "cross-workspace technology spill: " + value for value in technology_spill
            )
            if (
                profile.get("repository_kind") == "documentation"
                or report["policy"].get("scope_policies", {}).get(scope, {}).get("effective")
                == "documentation"
            ):
                failures.append("manifest workspace misclassified as documentation")
            if not read_only:
                failures.append("proposal modified extracted manifests or installed files")
            if any(entry["source"] != "bundled" for entry in own_selected):
                failures.append("offline proposal selected non-bundled skills")
            provenance = json.loads(
                (fixtures / spec["slug"] / "provenance.json").read_text(encoding="utf-8")
            )
            result.update(
                {
                    "scope": scope,
                    "technologies": technologies,
                    "expected_technologies": spec["expected_technologies"],
                    "expected_slots": spec["expected_slots"],
                    "selected_slots": sorted(actual_slots),
                    "repository_kind": profile.get("repository_kind"),
                    "read_only": read_only,
                    "manifest_sha256": provenance["manifest_sha256"],
                    "manifest_url": provenance["manifest_url"],
                    "license_url": provenance["license_url"],
                    "github_reported_license_spdx": provenance["github_reported_license_spdx"],
                    "license_review": provenance["license_review"],
                    "passed": not failures,
                }
            )
    for result in results:
        result.setdefault("passed", False)
    return {
        "schema_version": 1,
        "evidence_scope": LIMITATION,
        "network_used_for_verification": False,
        "upstream_execution": False,
        "refresh_failures": catalog.get("refresh_failures", []),
        "repositories": results,
        "passed": all(result["passed"] for result in results)
        and not catalog.get("refresh_failures"),
    }


def markdown_report(report):
    rows = [
        "# Real repository manifest matrix",
        "",
        LIMITATION,
        "",
        "Offline verification checks pinned identities, copied manifest/license SHA-256 values, expected technologies, selected language/build skills, documentation classification, workspace language isolation and read-only proposals.",
        "",
        "| Repository | Pinned commit | Manifest | Result |",
        "| --- | --- | --- | --- |",
    ]
    for item in report["repositories"]:
        repo, sha = item["repository"], item["commit"]
        status = "PASS" if item["passed"] else "FAIL: " + "; ".join(item["failures"])
        rows.append(
            f"| [{repo}](https://github.com/{repo}/tree/{sha}) | `{sha}` | `{item['original_path']}` | {status} |"
        )
    rows.extend(
        [
            "",
            "All copied files retain their upstream license in `fixtures/real-repositories/<slug>/LICENSE.txt`; each provenance record links the exact pinned original files. Refresh is explicit (`python tools/verify_real_repositories.py --refresh`) and uses a request limit, per-request timeout, total deadline and file-size cap. Default verification never accesses the network.",
            "",
        ]
    )
    reviewed = [item for item in report["repositories"] if item.get("license_review")]
    if reviewed:
        rows.extend(
            [
                "GitHub license detection returned `NOASSERTION` for the following notices. Their applicable licenses were reviewed against the pinned upstream text; each review is bound to the copied notice's SHA-256:",
                "",
            ]
        )
        for item in reviewed:
            rows.append(
                f"- [{item['repository']}]({item['license_url']}), {item['license_spdx']}: {item['license_review']['basis']}"
            )
        rows.append("")
    for failure in report.get("refresh_failures", []):
        rows.append(f"- Refresh failure: {failure['repository']}: {failure['reason']}")
    return "\n".join(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="explicitly fetch fresh public commit pins, manifests and licenses",
    )
    parser.add_argument(
        "--output", type=Path, default=WORKSPACE / "reports" / "real-repositories.json"
    )
    args = parser.parse_args(argv)
    if args.refresh:
        refresh()
    report = assess_repositories()
    write_json(args.output, report)
    args.output.with_suffix(".md").write_text(markdown_report(report), encoding="utf-8")
    passed = sum(item["passed"] for item in report["repositories"])
    print(
        f"Pinned real-manifest matrix: {passed}/{len(report['repositories'])} passed; report: {args.output.name}"
    )
    for item in report["repositories"]:
        if item["failures"]:
            print(f"{item['repository']}: {'; '.join(item['failures'])}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
