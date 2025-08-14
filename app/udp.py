from __future__ import annotations
import asyncio
import logging
import os
from typing import Callable, Optional, Tuple

from meshtastic.protobuf import mesh_pb2, portnums_pb2
from google.protobuf.message import DecodeError
from meshtastic import protocols
from mudp.singleton import conn
from mudp.encryption import decrypt_packet
from mudp import node, send_text_message, send_nodeinfo as _send_nodeinfo

from . import config

OnTextCb = Callable[[str], None]
UDP_VERBOSE = config.UDP_VERBOSE

def _vprint(*args, **kwargs):
    if UDP_VERBOSE:
        print(*args, **kwargs)

def setup_node(log: logging.Logger) -> None:
    node.node_id = config.MESHTASTIC_NODE_ID
    node.long_name = config.MESHTASTIC_LONG_NAME
    node.short_name = config.MESHTASTIC_SHORT_NAME
    node.channel = config.MESHTASTIC_CHANNEL
    node.key = config.MESHTASTIC_KEY

    conn.setup_multicast(config.MCAST_GRP, config.MCAST_PORT)
    log.info("mudp configured for %s:%d", config.MCAST_GRP, config.MCAST_PORT)

def send_text(msg: str, log) -> None:
    send_text_message(msg, num_hops=config.MESHTASTIC_HOP_LIMIT)

def send_nodeinfo(log) -> None:
    _send_nodeinfo(num_hops=config.MESHTASTIC_HOP_LIMIT)

def _is_text_message_app(portnum: int | None) -> bool:
    return portnum == getattr(portnums_pb2.PortNum, "TEXT_MESSAGE_APP", None)


def _decode_datagram_text_only(
    data: bytes,
    key: str,
    addr: Tuple[str, int],
) -> Tuple[Optional[str], Optional[mesh_pb2.MeshPacket]]:
    mp = mesh_pb2.MeshPacket()
    mp.ParseFromString(data)

    # Decrypt if needed
    if mp.HasField("encrypted") and not mp.HasField("decoded"):
        try:
            decoded_data = decrypt_packet(mp, key)
        except Exception as e:
            _vprint(f"[UDP][RX] decrypt_packet exception: {e!r}")
            return (None, None)
        if decoded_data is not None:
            mp.decoded.CopyFrom(decoded_data)
        else:
            _vprint("[UDP][RX] Failed to decrypt message — decoded_data is None")
            return (None, mp)

    if not mp.HasField("decoded"):
        return (None, None)

    portnum = mp.decoded.portnum
    if not _is_text_message_app(portnum):
        # Ignore everything except TEXT_MESSAGE_APP
        _vprint(f"[UDP][RX] ignore portnum={portnum} (not TEXT_MESSAGE_APP)")
        return (None, None)

    payload = mp.decoded.payload if isinstance(mp.decoded.payload, (bytes, bytearray)) else b""

    out_text: Optional[str] = None
    handler = protocols.get(portnum) if portnum is not None else None
    factory = getattr(handler, "protobufFactory", None) if handler is not None else None
    if callable(factory):
        try:
            pb = factory()
            pb.ParseFromString(payload)
            # Prefer pb.text if present
            txt = getattr(pb, "text", None)
            if isinstance(txt, (bytes, bytearray)):
                txt = txt.decode("utf-8", "ignore")
            if isinstance(txt, str) and txt.strip():
                out_text = txt.strip()
            # Mirror example: stringify payload for printing
            pb_str = str(pb).replace("\n", " ").replace("\r", " ").strip()
            mp.decoded.payload = pb_str.encode("utf-8")
        except Exception as e:
            _vprint(f"[UDP][RX] factory.ParseFromString {type(e).__name__}: {e}")

    # Fallback: if we still don't have text, treat decoded.payload as UTF-8
    if out_text is None and payload:
        try:
            s = payload.decode("utf-8", "ignore").strip()
            if s:
                out_text = s
        except Exception:
            pass

    return (out_text, mp)

class UdpReceiver:
    def __init__(self, group: str, port: int, log: logging.Logger, on_text: OnTextCb | None = None) -> None:
        self.group = group
        self.port = port
        self.log = log
        self.on_text = on_text
        self._reader_added = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()

        # Ensure conn.socket exists and is non-blocking for add_reader
        if getattr(conn, "socket", None) is None:
            conn.setup_multicast(self.group, self.port)
        try:
            conn.socket.setblocking(False)
        except Exception:
            pass

        def _on_readable():
            try:
                while True:
                    data, addr = conn.recvfrom(65535)
                    try:
                        text, mp = _decode_datagram_text_only(data, node.key, addr)
                    except Exception as e:
                        self.log.info("[UDP] UDP decode error: %r", e, exc_info=True)
                        continue

                    if text and self.on_text:
                        try:
                            _vprint(f"[UDP][RX] [RECV from {addr}] calling on_text: {text!r}")
                            self.on_text(text)
                        except Exception:
                            self.log.exception("[UDP] on_text callback failed")

            except (BlockingIOError, InterruptedError):
                pass
            except Exception as e:
                self.log.exception(f"[UDP] Error in UDP read loop: {type(e).__name__}: {e}")

        self._loop.add_reader(conn.socket.fileno(), _on_readable)
        self._reader_added = True
        self.log.info("[UDP] Async UDP reader started")

    def stop(self) -> None:
        if self._loop and self._reader_added:
            try:
                self._loop.remove_reader(conn.socket.fileno())
            except Exception:
                pass
        self._reader_added = False
        self.log.info("[UDP] Async UDP reader stopped")
