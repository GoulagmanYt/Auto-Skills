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
        # Pin reviewed prose, including preservation of the user's reasoning preference.
        self.assertEqual(
            hashlib.sha256(json.dumps(RULES, sort_keys=True).encode()).hexdigest(),
            "2cc4f1062b65e772db4bc926eeb2a87529b9c9d96b22b822964d9c37d52aaf3a",
        )
