import unittest


class NativeHookTests(unittest.TestCase):
    def test_only_exact_manager_session_hooks_receive_native_trust(self):
        from codex_bootstrap.native_hooks import trusted_overrides

        expected = {
            "SessionStart": "python -I -m codex_bootstrap.hooks",
            "UserPromptSubmit": "python -I -m codex_bootstrap.hooks",
        }
        own = {
            "source": "sessionFlags",
            "eventName": "sessionStart",
            "handlerType": "command",
            "command": expected["SessionStart"],
            "key": "flags:session_start:0:0",
            "currentHash": "sha256:" + "a" * 64,
        }
        external = {**own, "source": "project", "key": "repo:session_start:0:0"}
        other = {**own, "command": "evil", "key": "flags:session_start:0:1"}
        result = trusted_overrides(expected, {"data": [{"hooks": [own, external, other]}]})
        self.assertEqual(len(result), 2)
        self.assertIn("flags:session_start:0:0", result[1])
        self.assertNotIn("repo:", str(result))
        self.assertNotIn("bypass", str(result))

    def test_malformed_native_hash_is_rejected(self):
        from codex_bootstrap.native_hooks import trusted_overrides

        with self.assertRaises(ValueError):
            trusted_overrides(
                {"SessionStart": "ours"},
                {
                    "data": [
                        {
                            "hooks": [
                                {
                                    "source": "sessionFlags",
                                    "eventName": "sessionStart",
                                    "handlerType": "command",
                                    "command": "ours",
                                    "key": "x",
                                    "currentHash": "bad",
                                }
                            ]
                        }
                    ]
                },
            )


if __name__ == "__main__":
    unittest.main()
