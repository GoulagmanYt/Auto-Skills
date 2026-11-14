"""F9 dashboard hosted around the unmodified native Codex terminal."""

import os
import queue
import re
import shutil
import sys
import threading
import time
from contextlib import contextmanager

from .console_process import spawn_console
from .dashboard import native_integrations, render, snapshot

TERMINAL_RESET = b"\x1b[0m\x1b[?25h\x1b[?2026l\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1004l\x1b[?1006l\x1b[?2004l\x1b[?9001l\x1b[<u\x1b[?1049l"


def interactive_launch(args):
    if (
        os.environ.get("CODEX_BOOTSTRAP_DASHBOARD") == "0"
        or not sys.stdin.isatty()
        or not sys.stdout.isatty()
    ):
        return False
    values = {
        "-m",
        "--model",
        "-p",
        "--profile",
        "-C",
        "--cd",
        "-c",
        "--config",
        "--sandbox",
        "-s",
        "--ask-for-approval",
        "-a",
        "--add-dir",
        "--image",
        "-i",
        "--enable",
        "--disable",
    }
    skip = False
    for arg in args:
        if skip:
            skip = False
        elif arg in values:
            skip = True
        elif arg == "--":
            return True
        elif not arg.startswith("-"):
            return arg not in {
                "exec",
                "e",
                "review",
                "login",
                "logout",
                "mcp",
                "plugin",
                "app-server",
                "completion",
                "help",
                "update",
                "doctor",
                "features",
                "debug",
            }
    return True


class InputDecoder:
    """Recognize a split F9 sequence, while forwarding bracketed paste verbatim."""

    keys = (b"\x1b[20~", b"\x1b[20;1~", b"\x1b[57372u", b"\x1b[57372;1u")
    begin, end = b"\x1b[200~", b"\x1b[201~"

    def __init__(self):
        self.pending = b""
        self.pasting = False

    def feed(self, data):
        self.pending += data
        events = []

        def emit(data):
            if data:
                if events and events[-1][0] == "input":
                    events[-1] = ("input", events[-1][1] + data)
                else:
                    events.append(("input", data))

        while self.pending:
            if self.pasting:
                index = self.pending.find(self.end)
                if index >= 0:
                    emit(self.pending[: index + len(self.end)])
                    self.pending = self.pending[index + len(self.end) :]
                    self.pasting = False
                    continue
                keep = max(
                    (n for n in range(1, len(self.end)) if self.pending.endswith(self.end[:n])),
                    default=0,
                )
                emit(self.pending[:-keep] if keep else self.pending)
                self.pending = self.pending[-keep:] if keep else b""
                break
            windows = re.match(rb"\x1b\[(\d+);(\d+);(\d+);(\d+);(\d+);(\d+)_", self.pending)
            if windows:
                sequence = windows[0]
                if int(windows[1]) == 120:
                    if int(windows[4]):
                        events.append(("toggle", b""))
                else:
                    events.append(("input", sequence))
                self.pending = self.pending[len(sequence) :]
                continue
            if self.pending.startswith(self.begin):
                emit(self.begin)
                self.pending = self.pending[len(self.begin) :]
                self.pasting = True
                continue
            match = next((key for key in self.keys if self.pending.startswith(key)), None)
            if match:
                self.pending = self.pending[len(match) :]
                events.append(("toggle", b""))
            elif any(
                key.startswith(self.pending) for key in (*self.keys, self.begin)
            ) or re.fullmatch(rb"\x1b\[[0-9;]{0,100}", self.pending):
                break
            else:
                emit(self.pending[:1])
                self.pending = self.pending[1:]
        return events

    def flush(self):
        if self.pasting:
            return []
        data, self.pending = self.pending, b""
        return [("input", data)] if data else []


class PanelState:
    def __init__(self):
        self.open, self.tab, self.offset = False, 0, 0
        self.suppressed_releases = set()

    def handle(self, kind, data):
        windows = re.fullmatch(rb"\x1b\[(\d+);(\d+);(\d+);(\d+);(\d+);(\d+)_", data)
        if windows:
            key = int(windows[1])
            if not int(windows[4]) and key in self.suppressed_releases:
                self.suppressed_releases.discard(key)
                return "ignore"
            if self.open and int(windows[4]):
                self.suppressed_releases.add(key)
        if kind == "toggle":
            self.open = not self.open
            return "redraw" if self.open else "restore"
        if not self.open:
            return "forward"

        def windows_key(match):
            if not int(match[4]):
                return b""
            code = int(match[3])
            if code:
                return chr(code).encode("utf-8") if code <= 0x10FFFF else b""
            return {38: b"\x1b[A", 40: b"\x1b[B"}.get(int(match[1]), b"")

        data = re.sub(rb"\x1b\[(\d+);(\d+);(\d+);(\d+);(\d+);(\d+)_", windows_key, data)
        data = re.sub(
            rb"\x1b\[(\d+)(?:;[\d:]+)?u",
            lambda m: chr(int(m[1])).encode() if int(m[1]) < 128 else b"",
            data,
        )
        if data in {b"\x1b", b"q", b"Q"}:
            self.open = False
            return "restore"
        if data in {b"1", b"2", b"3", b"\t"}:
            self.tab = (self.tab + 1) % 3 if data == b"\t" else int(data) - 1
            self.offset = 0
        elif data == b"\x1b[A":
            self.offset = max(0, self.offset - 1)
        elif data == b"\x1b[B":
            self.offset += 1
        elif data in {b"r", b"R"}:
            return "refresh"
        return "redraw"


@contextmanager
def raw_terminal():
    if os.name == "nt":
        import ctypes as c
        import msvcrt
        from ctypes import wintypes as w

        from .windows_console import checked, kernel_api

        api = kernel_api()
        modes, binary = [], []
        pages = api.GetConsoleCP(), api.GetConsoleOutputCP()
        try:
            for stream, identifier in ((sys.stdin, -10), (sys.stdout, -11)):
                handle = api.GetStdHandle(identifier)
                mode = w.DWORD()
                checked(api.GetConsoleMode(handle, c.byref(mode)))
                modes.append((handle, mode.value))
                checked(
                    api.SetConsoleMode(
                        handle,
                        (mode.value & ~0x47) | 0x280 if identifier == -10 else mode.value | 4,
                    )
                )
                binary.append((stream.fileno(), msvcrt.setmode(stream.fileno(), os.O_BINARY)))
            checked(api.SetConsoleCP(65001))
            checked(api.SetConsoleOutputCP(65001))
            yield
        finally:
            for fd, mode in reversed(binary):
                msvcrt.setmode(fd, mode)
            for handle, mode in reversed(modes):
                api.SetConsoleMode(handle, mode)
            api.SetConsoleCP(pages[0])
            api.SetConsoleOutputCP(pages[1])
    else:
        import termios
        import tty

        fd = sys.stdin.fileno()
        settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            yield
        finally:
            termios.tcsetattr(fd, termios.TCSANOW, settings)


def run_terminal(command, root, *, env, cwd=None, inventory_command=None, start_open=False):
    events = queue.Queue(maxsize=256)
    stopping = threading.Event()
    tail = bytearray()
    panel, decoder = PanelState(), InputDecoder()
    integrations = {"plugins": [], "mcp": [], "errors": []}
    checking = False
    size = shutil.get_terminal_size((100, 30))
    session = env.get("CODEX_BOOTSTRAP_OBSERVATION_SESSION", "")

    def send(kind, data):
        while not stopping.is_set():
            try:
                events.put((kind, data), timeout=0.1)
                return
            except queue.Full:
                pass

    def drain(read, kind):
        try:
            while (kind == "output" or not stopping.is_set()) and (data := read()):
                if kind == "output" and stopping.is_set():
                    tail.extend(data)
                    del tail[:-1_000_000]
                else:
                    send(kind, data)
        except OSError:
            pass
        finally:
            send(kind + "_eof", b"")

    def refresh():
        send("inventory", native_integrations(inventory_command or command[:1], env=env, cwd=cwd))

    def display():
        try:
            report = snapshot(root, session=session, integrations=integrations)
            text = render(
                report,
                tab=panel.tab,
                width=max(1, size.columns - 1),
                height=size.lines,
                offset=panel.offset,
            )
        except (OSError, ValueError, TypeError, KeyError):
            text = "AUTO-SKILLS | F9 / Esc : retour\nEtat indisponible. R : actualiser."
        os.write(
            sys.stdout.fileno(),
            b"\x1b[?25l\x1b[0m\x1b[H\x1b[2J" + text.replace("\n", "\r\n").encode("utf-8"),
        )

    with raw_terminal():
        child = spawn_console(command, env=env, cwd=cwd, size=size)
        reader = threading.Thread(target=drain, args=(child.read, "output"), daemon=True)
        reader.start()

        def read_keyboard():
            if os.name != "nt":
                return os.read(sys.stdin.fileno(), 4096)
            import ctypes as c
            from ctypes import wintypes as w

            from .windows_console import checked, kernel_api

            api = kernel_api()
            buffer, count = c.create_string_buffer(4096), w.DWORD()
            # CRT _read holds the descriptor lock, blocking setmode on shutdown.
            checked(api.ReadFile(api.GetStdHandle(-10), buffer, len(buffer), c.byref(count), None))
            return buffer.raw[: count.value]

        threading.Thread(target=drain, args=(read_keyboard, "input"), daemon=True).start()
        redraw_at, restore_at, input_at = 0.0, 0.0, 0.0
        if start_open:
            panel.open = True
            display()
        try:
            while child.poll() is None:
                now = time.monotonic()
                actual = shutil.get_terminal_size((100, 30))
                if actual != size:
                    size = actual
                    child.resize(size)
                    redraw_at = 0
                if restore_at and now >= restore_at:
                    child.resize(size)
                    restore_at = 0
                if panel.open and now >= redraw_at:
                    display()
                    redraw_at = now + 1
                try:
                    kind, data = events.get(timeout=0.05)
                except queue.Empty:
                    if decoder.pending and now - input_at > 0.08:
                        pending = decoder.flush()
                    else:
                        continue
                else:
                    if kind == "output":
                        if not panel.open:
                            os.write(sys.stdout.fileno(), data)
                        continue
                    if kind == "inventory":
                        integrations, checking, redraw_at = data, False, 0
                        integrations["loaded"] = True
                        continue
                    if kind == "input_eof":
                        break
                    if kind != "input":
                        continue
                    input_at = now
                    pending = decoder.feed(data)
                for kind, data in pending:
                    action = panel.handle(kind, data)
                    if action == "forward":
                        child.write(data)
                    elif action == "restore":
                        os.write(sys.stdout.fileno(), b"\x1b[0m\x1b[2J\x1b[H\x1b[?25h")
                        child.resize((size.columns, max(1, size.lines - 1)))
                        restore_at = now + 0.08
                    elif action != "ignore":
                        redraw_at = 0
                        if not checking and (action == "refresh" or not integrations.get("loaded")):
                            checking = True
                            integrations["loaded"] = True
                            threading.Thread(target=refresh, daemon=True).start()
            code = child.poll()
            return code if code is not None else 130
        finally:
            stopping.set()
            child.close()
            reader.join(timeout=2)
            while not events.empty():
                kind, data = events.get_nowait()
                if kind == "output" and not panel.open:
                    os.write(sys.stdout.fileno(), data)
            if tail and not panel.open:
                os.write(sys.stdout.fileno(), tail)
            # A child may have exited while its final alternate-screen reset was hidden.
            os.write(sys.stdout.fileno(), TERMINAL_RESET)
