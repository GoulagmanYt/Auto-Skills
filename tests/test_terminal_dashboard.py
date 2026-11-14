import unittest

from suite_support import IsolatedTestCase


class TerminalDashboardTests(IsolatedTestCase):
    def test_coalesced_posix_keys_close_panel_and_preserve_following_input(self):
        from codex_bootstrap.terminal_dashboard import InputDecoder, PanelState, panel_events

        decoder, panel = InputDecoder(), PanelState()
        panel.handle("toggle", b"")
        forwarded = []
        for kind, data in panel_events(decoder.feed(b"qZ\r"), panel):
            if panel.handle(kind, data) == "forward":
                forwarded.append(data)
        self.assertFalse(panel.open)
        self.assertEqual(b"".join(forwarded), b"Z\r")

    def test_split_bracketed_paste_cannot_close_panel_or_submit_commands(self):
        from codex_bootstrap.terminal_dashboard import InputDecoder, PanelState, panel_events

        decoder, panel = InputDecoder(), PanelState()
        panel.handle("toggle", b"")
        paste = b"\x1b[200~qZ\r\x1b[20~\x1b[201~"
        for part in (paste[:8], paste[8:14], paste[14:]):
            for kind, data in panel_events(decoder.feed(part), panel):
                self.assertEqual(panel.handle(kind, data), "ignore")
        self.assertTrue(panel.open)

    def test_windows_surrogate_key_records_do_not_crash_open_panel(self):
        from codex_bootstrap.terminal_dashboard import PanelState

        panel = PanelState()
        panel.handle("toggle", b"")
        self.assertEqual(
            panel.handle("input", b"\x1b[0;0;55357;1;0;1_\x1b[0;0;56832;1;0;1_"), "redraw"
        )
        self.assertTrue(panel.open)

    def test_dashboard_key_release_is_not_forwarded_after_close(self):
        from codex_bootstrap.terminal_dashboard import InputDecoder, PanelState

        decoder, panel = InputDecoder(), PanelState()
        panel.handle("toggle", b"")
        actions = [
            panel.handle(kind, data)
            for kind, data in decoder.feed(b"\x1b[81;16;113;1;0;1_\x1b[81;16;113;0;0;1_")
        ]
        self.assertNotIn("forward", actions)

    def test_windows_keyboard_records_toggle_once_and_decode_panel_keys(self):
        from codex_bootstrap.terminal_dashboard import InputDecoder, PanelState

        decoder, panel = InputDecoder(), PanelState()
        self.assertEqual(decoder.feed(b"\x1b[120;67;0;"), [])
        self.assertEqual(decoder.feed(b"1;0;1_\x1b[120;67;0;0;0;1_"), [("toggle", b"")])
        panel.handle("toggle", b"")
        self.assertEqual(
            panel.handle("input", b"\x1b[81;16;113;1;0;1_\x1b[81;16;113;0;0;1_"), "restore"
        )

    def test_shortcut_is_recognized_across_reads_and_inside_paste_is_preserved(self):
        from codex_bootstrap.terminal_dashboard import InputDecoder

        decoder = InputDecoder()
        self.assertEqual(decoder.feed(b"hello\x1b[2"), [("input", b"hello")])
        self.assertEqual(decoder.feed(b"0~"), [("toggle", b"")])
        paste = b"\x1b[200~text\x1b[20~\x1b[201~"
        self.assertEqual(decoder.feed(paste), [("paste", paste)])

    def test_close_does_not_deliver_dashboard_keys_to_codex(self):
        from codex_bootstrap.terminal_dashboard import PanelState

        panel = PanelState()
        self.assertEqual(panel.handle("toggle", b""), "redraw")
        self.assertTrue(panel.open)
        self.assertEqual(panel.handle("input", b"2"), "redraw")
        self.assertEqual(panel.tab, 1)
        self.assertEqual(panel.handle("input", b"q"), "restore")
        self.assertFalse(panel.open)

    def test_noninteractive_and_exec_launches_bypass_the_terminal_host(self):
        from unittest.mock import patch

        from codex_bootstrap.terminal_dashboard import interactive_launch

        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("sys.stdout.isatty", return_value=True),
        ):
            self.assertTrue(interactive_launch(["resume", "--last"]))
            self.assertFalse(interactive_launch(["exec", "work"]))
            self.assertFalse(interactive_launch(["-m", "exec", "exec", "work"]))
        with patch("sys.stdin.isatty", return_value=False):
            self.assertFalse(interactive_launch([]))


if __name__ == "__main__":
    unittest.main()
