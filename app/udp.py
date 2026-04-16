from __future__ import annotations

import logging

from mudp import node, conn, send_text_message, send_nodeinfo as _send_nodeinfo

from . import config

log = logging.getLogger(__name__)


def setup_node() -> None:
    # Initialize multicast socket
    conn.setup_multicast(config.MCAST_GRP, config.MCAST_PORT)
    log.info("[UDP] Multicast initialized: %s:%d", config.MCAST_GRP, config.MCAST_PORT)

    # Configure node identity
    node.node_id = config.MESHTASTIC_NODE_ID
    node.long_name = config.MESHTASTIC_LONG_NAME
    node.short_name = config.MESHTASTIC_SHORT_NAME
    node.channel = config.MESHTASTIC_CHANNEL
    node.key = config.MESHTASTIC_KEY
    log.info("[UDP] Node setup complete: %s (%s)", config.MESHTASTIC_LONG_NAME, config.MESHTASTIC_NODE_ID)


def send_text(msg: str, packet_id: int) -> None:
    send_text_message(msg, hop_limit=config.MESHTASTIC_HOP_LIMIT, packet_id=packet_id)


def send_nodeinfo() -> None:
    _send_nodeinfo(hop_limit=config.MESHTASTIC_HOP_LIMIT)
