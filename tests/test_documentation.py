import tempfile
from pathlib import Path

from suite_support import IsolatedTestCase


class DocumentationTests(IsolatedTestCase):
    def test_link_check_resolves_relative_files_and_keeps_external_evidence(self):
        from tools.check_docs import missing_links

        self.assertEqual(
            missing_links(
                "docs/guide.md",
                "[ok](../README.md#start) [external](https://example.org/evidence) [anchor](#local)",
                {"README.md"},
            ),
            [],
        )
        self.assertEqual(
            missing_links("docs/guide.md", "[missing](../reports/absent.json)", {"README.md"}),
            ["docs/guide.md: missing target ../reports/absent.json"],
        )

    def test_links_cannot_escape_source_or_distribution_root(self):
        from tools.check_docs import missing_links

        self.assertEqual(len(missing_links("README.md", "[outside](../secret.md)", set())), 1)

    def test_documentation_directory_check_uses_its_own_root(self):
        from tools.check_docs import check_docs

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "README.md").write_text("[guide](docs/usage.md)")
            (root / "docs").mkdir()
            (root / "docs/usage.md").write_text("[back](../README.md)")
            self.assertEqual(check_docs(root), 2)
