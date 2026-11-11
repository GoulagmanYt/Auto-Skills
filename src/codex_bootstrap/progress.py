"""Plain stderr progress with a heartbeat during slow setup operations."""

import sys
import threading
import time


class Progress:
    def __init__(self, stream=None, interval=5):
        self.stream = stream if stream is not None else sys.stderr
        self.interval = interval
        self.started = time.monotonic()
        self.label = "Starting preparation"
        self.done = threading.Event()
        self.mutex = threading.Lock()
        self.thread = None

    def _write(self, label):
        with self.mutex:
            print(
                f"[Auto-Skills {time.monotonic() - self.started:.0f}s] {label}",
                file=self.stream,
                flush=True,
            )

    def stage(self, label):
        self.label = label
        self._write(label)

    def _heartbeat(self):
        while not self.done.wait(self.interval):
            self._write(self.label + " - still working")

    def __enter__(self):
        self.stage(self.label)
        self.thread = threading.Thread(target=self._heartbeat, daemon=True)
        self.thread.start()
        return self

    def finish(self, failed=False):
        if not self.done.is_set():
            self.done.set()
            if self.thread is not None:
                self.thread.join()
            self._write(
                "Setup failed; inspect the manager diagnostic" if failed else "Preparation complete"
            )

    def __exit__(self, kind, value, traceback):
        self.finish(failed=kind is not None)
