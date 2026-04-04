from __future__ import annotations
import logging
from pubsub import pub
from mudp import node, send_text_message, send_nodeinfo as _send_nodeinfo, UDPPacketStream

from . import config

_iface: UDPPacketStream | None = None
_on_text = None
log: logging.Logger = logging.getLogger(__name__)


def setup_node() -> None:
    node.node_id = config.MESHTASTIC_NODE_ID
    node.long_name = config.MESHTASTIC_LONG_NAME
    node.short_name = config.MESHTASTIC_SHORT_NAME
    node.channel = config.MESHTASTIC_CHANNEL
    node.key = config.MESHTASTIC_KEY
    log.info("[UDP] Node configured: %s (%s)", config.MESHTASTIC_LONG_NAME, config.MESHTASTIC_NODE_ID)


def send_text(msg: str, packet_id: int) -> None:
    send_text_message(msg, hop_limit=config.MESHTASTIC_HOP_LIMIT, packet_id=packet_id)


def send_nodeinfo() -> None:
    _send_nodeinfo(hop_limit=config.MESHTASTIC_HOP_LIMIT)


def start(on_text=None) -> None:
    global _iface, _on_text
    if _iface is not None:
        log.warning("[UDP] start() called but listener is already running — ignoring")
        return
    if on_text is not None:
        _on_text = on_text
        pub.subscribe(_on_text, "mesh.rx.text")
    _iface = UDPPacketStream(config.MCAST_GRP, config.MCAST_PORT, key=node.key)
    _iface.start()
    log.info("[UDP] Listener started on %s:%d", config.MCAST_GRP, config.MCAST_PORT)


def stop() -> None:
    global _iface, _on_text
    try:
        if _iface is not None:
            _iface.stop()
    finally:
        _iface = None
        if _on_text is not None:
            try:
                pub.unsubscribe(_on_text, "mesh.rx.text")
            except Exception:
                pass
            _on_text = None
        log.info("[UDP] Listener stopped")