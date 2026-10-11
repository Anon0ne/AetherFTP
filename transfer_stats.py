"""Transfer measurements; resumed bytes are excluded from throughput."""
import time


class TransferStats:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.started = clock()
        self.last_time = self.started
        self.initial = None
        self.done = 0
        self.total = 0
        self.last_bytes = 0
        self.rate = 0.0

    def update(self, done, total):
        now = self.clock()
        self.done, self.total = done, total
        if self.initial is None:
            self.initial = done
            self.last_bytes = done
            self.last_time = now
        elapsed = now - self.last_time
        if elapsed >= 0.2:
            self.rate = max(0, done - self.last_bytes) / elapsed / 1_000_000
            self.last_bytes, self.last_time = done, now
        return self.percent, self.rate

    @property
    def percent(self):
        return min(100, max(0, int(self.done * 100 / self.total))) if self.total else None

    def summary(self):
        elapsed = max(0, self.clock() - self.started)
        transferred = max(0, self.done - (self.initial or 0))
        return {'duration_seconds': round(elapsed, 3), 'bytes_transferred': transferred,
                'total_bytes': self.total, 'average_mbps': round(transferred / elapsed / 1_000_000, 3) if elapsed else 0.0}
