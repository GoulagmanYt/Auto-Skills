import unittest

from codex_bootstrap.profile import Profile
from codex_bootstrap.selection import Candidate, rejection


class ExternalQualityTests(unittest.TestCase):
    def skill(self, description, instructions):
        return Candidate(
            "performance",
            "performance-optimization",
            f"---\nname: performance-optimization\ndescription: {description}\n---\n{instructions}",
        )

    def test_game_performance_is_not_api_performance(self):
        candidate = self.skill(
            "Find and fix game performance problems.",
            "Use the engine profiler and a frame-time budget. Check object pooling, "
            "draw-call batching and shader variants. Measure the changed scene.",
        )
        self.assertIn(
            "game-development", rejection(candidate, Profile(technologies={"fastapi": "0.115"}))
        )
        self.assertIsNone(rejection(candidate, Profile(technologies={"unity": "6.3"})))

    def test_generic_profiling_can_include_a_game_example(self):
        candidate = self.skill(
            "Use when measuring application CPU and memory bottlenecks.",
            "Measure a representative workload. Compare baseline CPU and allocations. "
            "For example a game performance trace can reveal hot loops. Verify changes.",
        )
        self.assertIsNone(rejection(candidate, Profile(technologies={"fastapi": "0.115"})))

    def test_imported_react_192_apis_require_compatible_workspace_versions(self):
        candidate = Candidate(
            "framework-react",
            "react-patterns",
            "---\nname: react-patterns\ndescription: React rendering patterns.\n---\n"
            "Read React component boundaries and measure rendering. Verify subscriptions "
            "and cleanup with tests. Use the hooks described in the linked rules.",
            technologies={"react"},
            files={
                "rules/hooks.md": b"import { useEffectEvent } from 'react';\nUse it to read latest values."
            },
        )
        self.assertIn(
            "19.2",
            rejection(
                candidate, Profile(technologies={"react": "^18.3"}, slots=["framework-react"])
            ),
        )
        self.assertIn(
            "19.2",
            rejection(
                candidate, Profile(technologies={"react": "^19.0"}, slots=["framework-react"])
            ),
        )
        self.assertIsNone(
            rejection(
                candidate, Profile(technologies={"react": "^19.2"}, slots=["framework-react"])
            )
        )

    def test_trailmark_workflow_is_not_ready_without_its_runtime(self):
        candidate = Candidate(
            "token-context-pruning",
            "slicing-code-context",
            "---\nname: slicing-code-context\ndescription: Build graph-informed source slices with Trailmark.\n---\n"
            "Reduce the model context window using bounded source slices. Requires Python 3.12+ "
            "and Trailmark 0.5.x. Use uvx to generate graph packets before delegating analysis.",
        )
        profile = Profile(technologies={"python": "3.13"}, available_tools=["python", "uv"])
        self.assertIn("trailmark", rejection(candidate, profile))
        docs = Profile(technologies={}, available_tools=["python", "uv", "trailmark"])
        self.assertIn("source-code", rejection(candidate, docs))


if __name__ == "__main__":
    unittest.main()
