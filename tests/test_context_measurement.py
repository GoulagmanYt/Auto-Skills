import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.verify_context_savings import delta, prompt_metrics


class CharacterEncoding:
    """Predictable test counter, not the production tokenizer."""

    def encode(self, text, **kwargs):
        return list(text)


class ContextMeasurementTests(unittest.TestCase):
    def test_duplicate_skill_entries_remain_visible_in_native_measurement(self):
        section = (
            "<skills_instructions>\n### Available skills\n"
            "- python: Python guidance (file: .codex/skills/python/SKILL.md)\n"
            "- python: Python guidance (file: .agents/skills/python/SKILL.md)\n"
            "</skills_instructions>"
        )
        data = [
            {"id": "not-model-context", "type": "message", "content": [{"text": section}]},
            {"type": "additional_tools", "tools": [{"name": "read", "description": "Read"}]},
        ]
        process = SimpleNamespace(returncode=0, stdout=json.dumps(data), stderr="")
        with patch("tools.verify_context_savings.subprocess.run", return_value=process):
            result = prompt_metrics("codex", [], Path.cwd(), CharacterEncoding())
        self.assertEqual(result["visible_skills"], 2)
        self.assertEqual(result["unique_visible_skills"], 1)
        self.assertEqual(result["duplicate_skill_entries"], 1)
        self.assertEqual(result["text_tokens"], len(section))
        self.assertEqual(result["skill_catalog_tokens"], len(section))
        self.assertGreater(result["additional_tool_schema_tokens"], 0)

    def test_context_increase_is_reported_as_negative_savings(self):
        before = {"exposed_context_tokens": 100, "skill_catalog_tokens": 20, "visible_skills": 2}
        after = {"exposed_context_tokens": 120, "skill_catalog_tokens": 30, "visible_skills": 3}
        result = delta(before, after)
        self.assertEqual(result["exposed_context_tokens"]["saved"], -20)
        self.assertEqual(result["exposed_context_tokens"]["reduction_percent"], -20)

    def test_native_catalog_paths_expand_aliases_without_deduplicating(self):
        section = (
            "<skills_instructions>\n### Skill roots\n"
            "- `r0` = `<REPO>/.agents/skills`\n"
            "### Available skills\n"
            "- shared-name: First guide (file: r0/security/SKILL.md)\n"
            "- shared-name: Second guide (file: r0/architecture/SKILL.md)\n"
            "</skills_instructions>"
        )
        data = [{"content": [{"text": section}]}]
        process = SimpleNamespace(returncode=0, stdout=json.dumps(data), stderr="")
        with patch("tools.verify_context_savings.subprocess.run", return_value=process):
            result = prompt_metrics("codex", [], Path.cwd(), CharacterEncoding())
        self.assertEqual(
            result["skill_paths"],
            [
                "<REPO>/.agents/skills/security/SKILL.md",
                "<REPO>/.agents/skills/architecture/SKILL.md",
            ],
        )
        self.assertEqual(result["visible_skills"], 2)


if __name__ == "__main__":
    unittest.main()
