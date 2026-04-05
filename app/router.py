from __future__ import annotations
import logging
from collections import OrderedDict
from time import monotonic

from meshtastic.protobuf import mesh_pb2

from .udp import send_text
from .util import make_message_id

log = logging.getLogger(__name__)

class TTLSeen:
    def __init__(self, ttl_secs: float, maxsize: int = 5000) -> None:
        self.ttl = ttl_secs
        self.maxsize = maxsize
        self._d: OrderedDict[int, float] = OrderedDict()

    def add(self, key: int) -> None:
        now = monotonic()
        self._d[key] = now
        self._d.move_to_end(key)
        self._evict(now)

    def seen(self, key: int) -> bool:
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
        expired = [k for k, t in list(self._d.items()) if now - t > self.ttl]
        for k in expired:
            self._d.pop(k, None)


class Router:
    def __init__(self, ttl_secs: float) -> None:
        self.seen = TTLSeen(ttl_secs=ttl_secs)
        log.info("[ROUTER] Router initialized (ttl_secs=%s)", ttl_secs)

    @staticmethod
    def _norm(msg: str) -> str:
        return " ".join(msg.split())

    def mark_seen_from_udp(self, packet: mesh_pb2.MeshPacket, addr: object | None = None) -> None:
        """Called via pub.subscribe on mesh.rx.text — signature must match mudp's topic."""
        del addr
        try:
            self.seen.add(packet.id)
            log.info("[ROUTER] Message received: id=0x%08x", packet.id)
        except Exception:
            log.exception("[ROUTER] mark_seen_from_udp failed")

    def push(self, msg: str, seen_only: bool = False) -> None:
        normalized = self._norm(msg)
        key = make_message_id(normalized)
        if seen_only:
            self.seen.add(key)
            log.info("[ROUTER] New message marked as seen: id=0x%08x", key)
            return
        if self.seen.seen(key):
            log.info("[ROUTER] Message skipped (seen): id=0x%08x", key)
            return
        send_text(normalized, packet_id=key)
        self.seen.add(key)