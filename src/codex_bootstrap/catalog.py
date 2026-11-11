"""Small, self-contained fallback skills; never presented as downloaded results."""

import json
from importlib.resources import files

from .selection import Candidate

RULES = {
    key: tuple(value)
    for key, value in json.loads(
        files(__package__).joinpath("resources/guides.json").read_text(encoding="utf-8")
    ).items()
}


def rules_for(slot, profile):
    if slot in RULES:
        return RULES[slot]
    family, _, tech = slot.partition("-")
    version = profile.technologies.get(tech, "detected")
    context = f"Use for {tech} changes; detected constraint: {version}."
    specific = {
        "language": "Follow the language version and formatter configured by this project. Preserve type, error and resource ownership semantics. Validate input at public boundaries. Use the existing standard library and test conventions before adding dependencies.",
        "framework": "Confirm the installed framework major in the nearest manifest before selecting APIs. Follow the existing routing, rendering, lifecycle and dependency injection patterns. Keep server-only code and credentials out of clients. Verify the affected route/component and failure states with the existing tests.",
        "orm": "Read only the relevant schema, model and migration. Keep queries parameterized and transaction boundaries explicit. Avoid N+1 queries; bound result sets. Review generated SQL and migration reversibility. Verify constraints, nullability and concurrent updates using the project's database test conventions.",
        "database": "Inspect the relevant schema, constraints and query plan. Parameterize queries and bound pagination. Check index use and transaction isolation against the workload. Preserve data with additive migrations where possible. Test rollback, uniqueness and authorization at the application boundary.",
    }[family]
    return (
        context,
        specific
        + " Search symbols before reading bounded code ranges. Run the nearest existing check through token-run.",
    )


def bundled_candidates(profile):
    result = []
    for slot in profile.slots:
        description, body = rules_for(slot, profile)
        skill = f"---\nname: {slot}\ndescription: {json.dumps(description)}\n---\n\n{body}\n"
        result.append(Candidate(slot=slot, name=slot, body=skill, source="bundled", license="MIT"))
    return result
