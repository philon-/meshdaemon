from __future__ import annotations
from collections import OrderedDict
from time import monotonic
import logging
import asyncio
import uuid
import hashlib

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

    def __init__(self, ttl_secs: float, log: logging.Logger, hold_window, node_id, salt) -> None:
        self.seen = TTLSeen(ttl_secs=ttl_secs)
        self.log = log

        # Cooperative hold-off config (env-tunable, no external deps)
        self._hold_window = hold_window
        self._salt = (salt
                      or f"mac:{uuid.getnode():012x}"
                      or "")

        # Pending coordination
        self._pending_evt: dict[str, asyncio.Event] = {}
        self._pending_task: dict[str, asyncio.Task] = {}

        log.info("[ROUTER] Router initialized. ttl_secs=%d, hold_window=%.1f, salt=%r", ttl_secs, self._hold_window, self._salt)

    @staticmethod
    def _norm(msg: str) -> str:
        return " ".join(msg.split())  # normalize whitespace

    def _delay_for(self, key: str) -> float:
        if self._hold_window <= 0:
            return 0.0
        h = hashlib.blake2b(digest_size=8)
        h.update(key.encode("utf-8"))
        if self._salt:
            h.update(self._salt.encode("utf-8"))
        val = int.from_bytes(h.digest(), "big")
        # ensure at least 1s range to avoid mod 0
        return float(val % max(1, int(self._hold_window)))

    def _get_evt(self, key: str) -> asyncio.Event:
        evt = self._pending_evt.get(key)
        if evt is None:
            evt = asyncio.Event()
            self._pending_evt[key] = evt
        return evt

    def mark_seen(self, msg: str) -> None:
        key = self._norm(msg)
        self.seen.add(key)
        # wake/cancel any pending sender for this key
        evt = self._pending_evt.get(key)
        if evt and not evt.is_set():
            evt.set()

    def mark_seen_from_udp(self, msg: str) -> None:
        self.mark_seen(msg)

    async def _hold_and_send(self, key: str) -> None:
        try:
            # Already seen? nothing to do.
            if self.seen.seen(key):
                self.log.info("[ROUTER] Skip (seen): %r", key[:120])
                return

            delay = self._delay_for(key)
            evt = self._get_evt(key)

            if delay > 0:
                self.log.info("[ROUTER] Hold-off %.1fs before send: %r", delay, key[:120])
                try:
                    await asyncio.wait_for(evt.wait(), timeout=delay)
                    # Someone else sent it (or we heard it on UDP)
                    self.log.info("[ROUTER] Canceled (heard on UDP): %r", key[:120])
                    return
                except asyncio.TimeoutError:
                    # Our turn to send (timeout elapsed)
                    pass

                # Double-check in case it arrived just after timeout fired
                if self.seen.seen(key):
                    self.log.info("[ROUTER] Canceled (heard on UDP after timeout): %r", key[:120])
                    return
            # Send and mark seen immediately
            send_text(key, self.log)
            self.seen.add(key)
        finally:
            # cleanup pending state
            self._pending_evt.pop(key, None)
            self._pending_task.pop(key, None)

    def maybe_send(self, msg: str) -> None:
        key = self._norm(msg)
        if self.seen.seen(key):
            self.log.info("[ROUTER] Skip (seen): %r", key[:120])
            return

        # Coalesce: if a send is already pending for this key, don't schedule again
        t = self._pending_task.get(key)
        if t and not t.done():
            self.log.info("[ROUTER] Send already pending: %r", key[:120])
            return

        task = asyncio.create_task(self._hold_and_send(key), name=f"send:{key[:32]}")
        self._pending_task[key] = task

    def push(self, msg: str, seen_only: bool = False) -> None:
        if seen_only:
            self.mark_seen(msg)
        else:
            self.maybe_send(msg)
