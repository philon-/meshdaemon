from __future__ import annotations
import logging
from typing import Optional, Callable
from pubsub import pub
from meshtastic.protobuf import mesh_pb2, portnums_pb2
from mudp import node, conn, send_text_message, send_nodeinfo as _send_nodeinfo, UDPPacketStream

from . import config

OnTextCb = Callable[[str], None]

def setup_node(log: logging.Logger) -> None:
    node.node_id = config.MESHTASTIC_NODE_ID
    node.long_name = config.MESHTASTIC_LONG_NAME
    node.short_name = config.MESHTASTIC_SHORT_NAME
    node.channel = config.MESHTASTIC_CHANNEL
    node.key = config.MESHTASTIC_KEY
    conn.setup_multicast(config.MCAST_GRP, config.MCAST_PORT)
    log.info("[UDP] Configured for %s:%d", config.MCAST_GRP, config.MCAST_PORT)

def send_text(msg: str, log) -> None:
    send_text_message(msg, hop_limit=config.MESHTASTIC_HOP_LIMIT)

def send_nodeinfo(log) -> None:
    _send_nodeinfo(hop_limit=config.MESHTASTIC_HOP_LIMIT)

class PubSubReceiver:
    def __init__(self, log: logging.Logger, *, on_text: Optional[OnTextCb] = None) -> None:
        self.log = log
        self.on_text = on_text
        self._subscribed = False
        self._iface: Optional[UDPPacketStream] = None

    def _on_text_packet(self, packet: mesh_pb2.MeshPacket, addr=None) -> None:
        try:
            if not packet.HasField("decoded"):
                return
            if packet.decoded.portnum != portnums_pb2.PortNum.TEXT_MESSAGE_APP:
                return
            msg = packet.decoded.payload.decode("utf-8", "ignore").strip()
            if msg:
                self.log.info("[UDP][RX] %r", msg)
                if self.on_text:
                    self.on_text(msg)
        except Exception:
            self.log.exception("[UDP] on_text processing failed")

    def start(self) -> None:
        if self._subscribed:
            return
        # Start the UDP listener that publishes to pub/sub
        self._iface = UDPPacketStream(config.MCAST_GRP, config.MCAST_PORT, key=node.key)
        self._iface.start()

        # Subscribe to mudp topics
        pub.subscribe(self._on_text_packet, "mesh.rx.port.1")        # TEXT_MESSAGE_APP

        self._subscribed = True
        self.log.info("[UDP] PubSub listener started")

    def stop(self) -> None:
        if self._subscribed:
            try:
                pub.unsubscribe(self._on_text_packet, "mesh.rx.port.1")
            except Exception:
                pass
            self._subscribed = False
        if self._iface:
            try:
                self._iface.stop()
            except Exception:
                pass
            self._iface = None
        self.log.info("[UDP] PubSub listener stopped")
