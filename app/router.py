from __future__ import annotations
from collections import OrderedDict
from time import monotonic
import logging

from .udp import send_text

class TTLSeen:
    def __init__(self, ttl_secs: float, maxsize: int = 5000) -> None:
        self.ttl = ttl_secs
        self.maxsize = maxsize
        self._d: OrderedDict[str, float] = OrderedDict()

    def add(self, key: str) -> None:
        now = monotonic()
        self._d[key] = now
        self._d.move_to_end(key)
        self._evict(now)

    def seen(self, key: str) -> bool:
        ts = self._d.get(key)
        if ts is None:
            return False
        now = monotonic()
        if now - ts > self.ttl:
            self._d.pop(key, None)
            return False
        return True

    def _evict(self, now: float | None = None) -> None:
        if now is None:
            now = monotonic()
        while len(self._d) > self.maxsize:
            self._d.popitem(last=False)
        # opportunistic expiry
        expired = [k for k, t in list(self._d.items()) if now - t > self.ttl]
        for k in expired:
            self._d.pop(k, None)

class Router:

    def __init__(self, ttl_secs: float, log: logging.Logger) -> None:
        self.seen = TTLSeen(ttl_secs=ttl_secs)
        self.log = log
        log.info("[ROUTER] Router initialized with TTL: %d seconds", ttl_secs)


    @staticmethod
    def _norm(msg: str) -> str:
        return " ".join(msg.split())  # normalize whitespace

    def mark_seen(self, msg: str) -> None:
        key = self._norm(msg)
        self.seen.add(key)

    def mark_seen_from_udp(self, msg: str) -> None:
        self.mark_seen(msg)

    def maybe_send(self, msg: str) -> None:
        key = self._norm(msg)
        if self.seen.seen(key):
            self.log.info("Skip (seen): %r", key[:120])
            return
        send_text(key, self.log)
        self.seen.add(key)
