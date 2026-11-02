"""Worker memory policy: hard Linux address-space cap, sampled macOS RSS guard.

macOS does not enforce RLIMIT_AS. Its guard terminates a worker after sampled
peak RSS exceeds the cap; it is not an allocation-time sandbox. Input, CPU,
file, and parent wall-time limits remain in force on both platforms.
"""
from __future__ import annotations

import os
import resource
import sys
import threading


def limit_memory(max_bytes):
    if sys.platform != "darwin":
        resource.setrlimit(resource.RLIMIT_AS, (max_bytes, max_bytes))
        return

    def watch():
        while True:
            if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss > max_bytes:
                os._exit(70)  # Fail without exposing input or parser state.
            threading.Event().wait(0.02)

    threading.Thread(target=watch, daemon=True, name="worker-memory-guard").start()
