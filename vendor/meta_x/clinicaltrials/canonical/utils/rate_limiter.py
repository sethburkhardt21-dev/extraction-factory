from __future__ import annotations
import threading
import time

class RateLimiter:
    def __init__(self, rate_per_sec: float):
        if rate_per_sec < 0:
            raise ValueError("rate_per_sec must be >= 0")
        self.interval = 1.0 / rate_per_sec if rate_per_sec else 0.0
        self._last = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._last + self.interval - now
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
