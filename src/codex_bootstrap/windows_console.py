"""Windows ConPTY bridge. Imported only on Windows 10 1809 or newer."""

import ctypes as c
import os
from ctypes import wintypes as w

from .console_process import windows_command_line


class Coord(c.Structure):
    _fields_ = [("X", w.SHORT), ("Y", w.SHORT)]


class StartupInfo(c.Structure):
    _fields_ = [
        ("cb", w.DWORD),
        ("lpReserved", w.LPWSTR),
        ("lpDesktop", w.LPWSTR),
        ("lpTitle", w.LPWSTR),
        ("dwX", w.DWORD),
        ("dwY", w.DWORD),
        ("dwXSize", w.DWORD),
        ("dwYSize", w.DWORD),
        ("dwXCountChars", w.DWORD),
        ("dwYCountChars", w.DWORD),
        ("dwFillAttribute", w.DWORD),
        ("dwFlags", w.DWORD),
        ("wShowWindow", w.WORD),
        ("cbReserved2", w.WORD),
        ("lpReserved2", c.POINTER(w.BYTE)),
        ("hStdInput", w.HANDLE),
        ("hStdOutput", w.HANDLE),
        ("hStdError", w.HANDLE),
    ]


class StartupInfoEx(c.Structure):
    _fields_ = [("StartupInfo", StartupInfo), ("lpAttributeList", w.LPVOID)]


class ProcessInfo(c.Structure):
    _fields_ = [
        ("hProcess", w.HANDLE),
        ("hThread", w.HANDLE),
        ("dwProcessId", w.DWORD),
        ("dwThreadId", w.DWORD),
    ]


def kernel_api():
    api = c.WinDLL("kernel32", use_last_error=True)
    pointer = w.LPVOID
    signatures = {
        "CreatePipe": ([c.POINTER(w.HANDLE), c.POINTER(w.HANDLE), pointer, w.DWORD], w.BOOL),
        "CreatePseudoConsole": (
            [Coord, w.HANDLE, w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)],
            c.c_int32,
        ),
        "ResizePseudoConsole": ([w.HANDLE, Coord], c.c_int32),
        "ClosePseudoConsole": ([w.HANDLE], None),
        "InitializeProcThreadAttributeList": (
            [pointer, w.DWORD, w.DWORD, c.POINTER(c.c_size_t)],
            w.BOOL,
        ),
        "UpdateProcThreadAttribute": (
            [pointer, c.c_size_t, c.c_size_t, pointer, c.c_size_t, pointer, pointer],
            w.BOOL,
        ),
        "DeleteProcThreadAttributeList": ([pointer], None),
        "CreateProcessW": (
            [
                w.LPCWSTR,
                w.LPWSTR,
                pointer,
                pointer,
                w.BOOL,
                w.DWORD,
                pointer,
                w.LPCWSTR,
                c.POINTER(StartupInfoEx),
                c.POINTER(ProcessInfo),
            ],
            w.BOOL,
        ),
        "ReadFile": ([w.HANDLE, pointer, w.DWORD, c.POINTER(w.DWORD), pointer], w.BOOL),
        "WriteFile": ([w.HANDLE, pointer, w.DWORD, c.POINTER(w.DWORD), pointer], w.BOOL),
        "CloseHandle": ([w.HANDLE], w.BOOL),
        "WaitForSingleObject": ([w.HANDLE, w.DWORD], w.DWORD),
        "GetExitCodeProcess": ([w.HANDLE, c.POINTER(w.DWORD)], w.BOOL),
        "TerminateProcess": ([w.HANDLE, w.UINT], w.BOOL),
        "GetStdHandle": ([w.DWORD], w.HANDLE),
        "GetConsoleMode": ([w.HANDLE, c.POINTER(w.DWORD)], w.BOOL),
        "SetConsoleMode": ([w.HANDLE, w.DWORD], w.BOOL),
        "GetConsoleCP": ([], w.UINT),
        "GetConsoleOutputCP": ([], w.UINT),
        "SetConsoleCP": ([w.UINT], w.BOOL),
        "SetConsoleOutputCP": ([w.UINT], w.BOOL),
    }
    for name, (args, result) in signatures.items():
        function = getattr(api, name)
        function.argtypes, function.restype = args, result
    return api


def checked(value):
    if not value:
        raise c.WinError(c.get_last_error())
    return value


class WindowsConsole:
    def __init__(self, command, *, env, cwd, size):
        self.api = kernel_api()
        self.console, self.process, self.reader, self.writer = (w.HANDLE() for _ in range(4))
        incoming, outgoing = w.HANDLE(), w.HANDLE()
        attributes = None
        initialized = False
        try:
            checked(self.api.CreatePipe(c.byref(incoming), c.byref(self.writer), None, 0))
            checked(self.api.CreatePipe(c.byref(self.reader), c.byref(outgoing), None, 0))
            result = self.api.CreatePseudoConsole(
                Coord(*size), incoming, outgoing, 0, c.byref(self.console)
            )
            if result < 0:
                raise OSError(f"CreatePseudoConsole failed: {result:#x}")
            length = c.c_size_t()
            self.api.InitializeProcThreadAttributeList(None, 1, 0, c.byref(length))
            attributes = c.create_string_buffer(length.value)
            checked(self.api.InitializeProcThreadAttributeList(attributes, 1, 0, c.byref(length)))
            initialized = True
            checked(
                self.api.UpdateProcThreadAttribute(
                    attributes, 0, 0x00020016, self.console, c.sizeof(w.HANDLE), None, None
                )
            )
            startup = StartupInfoEx()
            startup.StartupInfo.cb = c.sizeof(startup)
            # Clear redirected parent stdio; ConPTY supplies the child's console.
            startup.StartupInfo.dwFlags = 0x00000100
            startup.lpAttributeList = c.cast(attributes, w.LPVOID)
            process = ProcessInfo()
            environment = dict(os.environ if env is None else env)
            block = c.create_unicode_buffer(
                "\0".join(
                    f"{k}={v}"
                    for k, v in sorted(environment.items(), key=lambda pair: pair[0].upper())
                )
                + "\0\0"
            )
            arguments = c.create_unicode_buffer(windows_command_line(command))
            checked(
                self.api.CreateProcessW(
                    None,
                    arguments,
                    None,
                    None,
                    False,
                    0x00080000 | 0x00000400,
                    block,
                    str(cwd) if cwd else None,
                    c.byref(startup),
                    c.byref(process),
                )
            )
            self.process = w.HANDLE(process.hProcess)
            self.api.CloseHandle(process.hThread)
        except BaseException:
            self.close()
            raise
        finally:
            if initialized:
                self.api.DeleteProcThreadAttributeList(attributes)
            for handle in (incoming, outgoing):
                if handle:
                    self.api.CloseHandle(handle)

    def read(self):
        buffer = c.create_string_buffer(65536)
        count = w.DWORD()
        if not self.api.ReadFile(self.reader, buffer, len(buffer), c.byref(count), None):
            if c.get_last_error() in {6, 109, 232, 995}:
                return b""
            raise c.WinError(c.get_last_error())
        return buffer.raw[: count.value]

    def write(self, data):
        while data:
            count = w.DWORD()
            checked(self.api.WriteFile(self.writer, data, len(data), c.byref(count), None))
            data = data[count.value :]

    def resize(self, size):
        if self.api.ResizePseudoConsole(self.console, Coord(*size)) < 0:
            raise OSError("could not resize native terminal")

    def poll(self):
        if not self.process or self.api.WaitForSingleObject(self.process, 0) == 0x102:
            return None
        code = w.DWORD()
        checked(self.api.GetExitCodeProcess(self.process, c.byref(code)))
        return code.value

    def close(self):
        if self.process and self.poll() is None:
            self.api.TerminateProcess(self.process, 130)
        if self.console:
            self.api.ClosePseudoConsole(self.console)
            self.console = w.HANDLE()
        for name in ("writer", "reader", "process"):
            handle = getattr(self, name)
            if handle:
                self.api.CloseHandle(handle)
                setattr(self, name, w.HANDLE())
