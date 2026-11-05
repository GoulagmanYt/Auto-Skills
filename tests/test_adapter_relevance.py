import unittest

from codex_bootstrap.profile import Profile
from codex_bootstrap.selection import Candidate, rejection


class AdapterRelevanceTests(unittest.TestCase):
    def test_new_ecosystem_hints_do_not_fill_unrelated_general_slots(self):
        for technology in ("cpp", "cmake", "flutter", "julia", "elixir"):
            with self.subTest(technology=technology):
                candidate = Candidate(
                    slot="unit-testing",
                    name=f"{technology}-testing",
                    remote_path=f"{technology}/SKILL.md",
                    repository="fixture/guides",
                    body=(
                        f"---\nname: {technology}-testing\ndescription: Review focused tests.\n---\n"
                        "Inspect the nearest manifest and existing test conventions. "
                        "Exercise public behavior, boundary values and error handling. "
                        "Run the relevant existing checks and preserve unrelated files."
                    ),
                )
                unrelated = Profile(technologies={"python": ">=3.11"}, slots=["unit-testing"])
                self.assertIsNotNone(rejection(candidate, unrelated))
