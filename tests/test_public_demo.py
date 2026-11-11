from suite_support import IsolatedTestCase


class PublicDemoTests(IsolatedTestCase):
    def test_frontend_update_preserves_backend_and_reports_isolation(self):
        from tools.demo_workspaces import demonstrate

        result = demonstrate()
        self.assertEqual(result["backend_workspace"], "backend")
        self.assertIn("language-rust", result["backend_active_slots"])
        self.assertNotIn("framework-react", result["backend_active_slots"])
        self.assertNotIn("build-vite", result["backend_active_slots"])
        self.assertTrue(result["backend_files_unchanged"])
        self.assertTrue(result["tools_unchanged"])
        self.assertIn("framework-react", result["refreshed_slots"])
        self.assertFalse(any("backend::" in slot for slot in result["refreshed_slots"]))
