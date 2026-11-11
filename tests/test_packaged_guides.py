import hashlib
import json
from importlib.resources import files

from suite_support import IsolatedTestCase


class PackagedGuideTests(IsolatedTestCase):
    def test_fallback_guides_are_packaged_and_keep_reviewed_content(self):
        from codex_bootstrap.catalog import RULES

        resource = files("codex_bootstrap").joinpath("resources/guides.json")
        self.assertTrue(resource.is_file())
        data = json.loads(resource.read_text(encoding="utf-8"))
        self.assertEqual({k: tuple(v) for k, v in data.items()}, RULES)
        self.assertTrue(
            all(
                len(v) == 2 and all(isinstance(s, str) and s.strip() for s in v)
                for v in data.values()
            )
        )
        # Pin prose through the extraction: refactoring must not rewrite instructions.
        self.assertEqual(
            hashlib.sha256(json.dumps(RULES, sort_keys=True).encode()).hexdigest(),
            "14779beef77f80d7c9346a37f809b06b389e1d04ffaca391068ad5e467c596a6",
        )
