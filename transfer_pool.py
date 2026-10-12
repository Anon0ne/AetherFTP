"""Separate protocol connections and shared bandwidth budgets per direction."""
import threading
import time
from collections import deque
from transfer_control import check_cancelled


class BandwidthLimiter:
    def __init__(self, mbps=0):
        self.condition = threading.Condition()
        self.rate = mbps * 1_000_000
        self.tokens = 0.0
        self.updated = time.monotonic()

    def set_limit(self, mbps):
        with self.condition:
            self.rate = mbps * 1_000_000
            self.tokens = 0.0
            self.updated = time.monotonic()
            self.condition.notify_all()

    def consume(self, amount, checkpoint=None):
        while amount > 0:
            if checkpoint: checkpoint()
            portion = min(amount, 65536)
            with self.condition:
                if self.rate:
                    now = time.monotonic()
                    self.tokens = min(max(65536, self.rate * .2), self.tokens + (now - self.updated) * self.rate)
                    self.updated = now
                    if self.tokens >= portion:
                        self.tokens -= portion
                    else:
                        self.condition.wait(min(.1, (portion - self.tokens) / self.rate))
                        continue
            amount -= portion


class TransferPool:
    def __init__(self, factory, run):
        self.factory, self.run = factory, run
        self.condition = threading.Condition()
        self.jobs = {'Upload': deque(), 'Download': deque()}
        self.limits = {'Upload': 1, 'Download': 1}
        self.bandwidth = {direction: BandwidthLimiter() for direction in self.limits}
        self.resources = set()
        self.clients = {}
        self.active_slots = set()
        self.active_cancellations = {}
        self.paused = False
        self.threads = []
        self.stopped = False

    def configure(self, settings):
        with self.condition:
            self.limits = {'Upload': settings['uploads'], 'Download': settings['downloads']}
            self.condition.notify_all()
        self.bandwidth['Upload'].set_limit(settings['upload_mbps'])
        self.bandwidth['Download'].set_limit(settings['download_mbps'])

    def submit(self, direction, resource, args, job, barrier=None, cancelled=None):
        with self.condition:
            if not self.threads:
                for kind in ('Upload', 'Download'):
                    for slot in range(8):
                        worker = threading.Thread(target=self.worker, args=(kind, slot), daemon=True)
                        self.threads.append(worker); worker.start()
            self.jobs[direction].append((direction, resource, args, job, barrier, cancelled))
            self.condition.notify_all()

    def wake(self):
        with self.condition: self.condition.notify_all()

    def set_paused(self, paused):
        with self.condition:
            self.paused = paused
            self.condition.notify_all()

    def checkpoint(self, cancelled=None):
        with self.condition:
            check_cancelled(cancelled)
            while self.paused:
                self.condition.wait(.1)
                check_cancelled(cancelled)

    def cancel(self, event):
        event.set()
        with self.condition:
            for slot, cancellation in self.active_cancellations.items():
                if cancellation is event and slot in self.clients:
                    client = self.clients[slot]
                    if hasattr(client, 'cancel'): client.cancel()
            self.condition.notify_all()

    def worker(self, direction, slot):
        client, connected_args = None, None
        try:
            while True:
                with self.condition:
                    while True:
                        if self.stopped: return
                        if client and (slot >= self.limits[direction] or
                                       (not any(self.jobs.values()) and not self.active_slots)):
                            client.close(); connected_args = None
                        candidate = None
                        if slot < self.limits[direction]:
                            for item in self.jobs[direction]:
                                cancelled = item[5] is not None and item[5].is_set()
                                if not cancelled and self.paused: continue
                                if item[4] is not None and not item[4].is_set() and not cancelled: break
                                if item[1] not in self.resources:
                                    candidate = item; break
                        if candidate:
                            self.jobs[direction].remove(candidate)
                            self.resources.add(candidate[1]); self.active_slots.add((direction, slot))
                            self.active_cancellations[(direction, slot)] = candidate[5]
                            break
                        self.condition.wait()
                _, resource, args, job, _, _ = candidate
                if client is None:
                    client = self.factory()
                    with self.condition: self.clients[(direction, slot)] = client
                try:
                    def ensure_connected():
                        nonlocal connected_args
                        if connected_args != args or client.conn is None:
                            client.close(); client.connect(*args); connected_args = args
                    self.run(client, ensure_connected, job)
                finally:
                    with self.condition:
                        self.resources.discard(resource); self.active_slots.discard((direction, slot))
                        self.active_cancellations.pop((direction, slot), None)
                        if not any(self.jobs.values()) and not self.active_slots:
                            self.close_idle_connections()
                        self.condition.notify_all()
        finally:
            if client: client.close()

    def close_idle_connections(self):
        with self.condition:
            for slot, client in self.clients.items():
                if slot not in self.active_slots: client.close()

    def shutdown(self):
        with self.condition:
            self.stopped = True; self.condition.notify_all()
        for thread in self.threads: thread.join(timeout=2)
