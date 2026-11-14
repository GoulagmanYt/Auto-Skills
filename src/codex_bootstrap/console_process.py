"""Native pseudo terminals, with no third-party runtime dependency."""

import os
import subprocess


def spawn_console(command, *, env, cwd, size):
    if os.name == "nt":
        from .windows_console import WindowsConsole

        return WindowsConsole(command, env=env, cwd=cwd, size=size)
    return PosixConsole(command, env=env, cwd=cwd, size=size)


class PosixConsole:
    def __init__(self, command, *, env, cwd, size):
        import pty

        self.code = None
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            try:
                if cwd:
                    os.chdir(cwd)
                os.execvpe(command[0], command, env if env is not None else os.environ)
            except OSError:
                os.write(2, b"Auto-Skills: native Codex launch failed\r\n")
                os._exit(127)
        self.resize(size)

    def read(self):
        import errno

        try:
            return os.read(self.fd, 65536)
        except OSError as exc:
            if exc.errno in {errno.EIO, errno.EBADF}:
                return b""
            raise

    def write(self, data):
        while data:
            data = data[os.write(self.fd, data) :]

    def resize(self, size):
        import fcntl
        import struct
        import termios

        width, height = size
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack("HHHH", height, width, 0, 0))

    def poll(self):
        if self.code is None:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid:
                code = os.waitstatus_to_exitcode(status)
                self.code = code if code >= 0 else 128 - code
        return self.code

    def close(self):
        import signal
        import time

        if self.fd is None:
            return
        if self.poll() is None:
            try:
                os.killpg(self.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            deadline = time.monotonic() + 1
            while self.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            if self.poll() is None:
                try:
                    os.killpg(self.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _, status = os.waitpid(self.pid, 0)
                code = os.waitstatus_to_exitcode(status)
                self.code = code if code >= 0 else 128 - code
        os.close(self.fd)
        self.fd = None


def windows_command_line(command):
    return subprocess.list2cmdline(command)
