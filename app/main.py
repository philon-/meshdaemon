from __future__ import annotations
import asyncio
import logging
import signal
import sys
from typing import Callable
import time
import aiohttp

from . import config
from .udp import setup_node, PubSubReceiver, send_nodeinfo
from .router import Router

# Sources
from .sources import vma, smhi

def make_push(router: Router) -> Callable[[str], None]:
    def _push(msg: str, seen_only: bool = False) -> None:
        if seen_only:
            router.mark_seen(msg)
        else:
            router.maybe_send(msg)
    return _push

def watch(task_name: str, task: asyncio.Task) -> None:
    def _done(t: asyncio.Task):
        try:
            t.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.getLogger("daemon").error("Task %s crashed: %r", task_name, e, exc_info=True)
    task.add_done_callback(_done)

async def nodeinfo_heartbeat(log: logging.Logger) -> None:
    log.info("[Nodeinfo] Broadcast interval started (interval=%ds)", config.MESHTASTIC_NODEINFO_INTERVAL)
    try:
        while True:
            await asyncio.sleep(config.MESHTASTIC_NODEINFO_INTERVAL)
            try:
                send_nodeinfo(log)
                log.info("[Nodeinfo] Sent")
            except Exception as e:
                log.warning("[Nodeinfo] Send failed: %r", e)
    except asyncio.CancelledError:
        log.info("[Nodeinfo] Broadcast interval stopped")
        raise

async def main() -> None:
    log = logging.getLogger("daemon")
    log.setLevel(logging.INFO)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(h)

    setup_node(log)
    send_nodeinfo(log)

    router = Router(ttl_secs=config.SEEN_TTL_SECS, log=log, hold_window=config.HOLD_WINDOW_SECS, node_id=config.MESHTASTIC_NODE_ID, salt=config.INSTANCE_SALT)

    # UDP RX to mark seen
    udp_rx = PubSubReceiver(log, on_text=router.mark_seen_from_udp)
    udp_rx.start()

    async with aiohttp.ClientSession() as session:
        push = make_push(router)

        # Start sources with warm-up (first fetch = mark seen only)
        t_vma  = asyncio.create_task(vma.run(session, log, warmup=config.WARMUP, push=push), name="src:vma")
        t_smhi = asyncio.create_task(smhi.run(session, log, warmup=config.WARMUP, push=push), name="src:smhi")
        t_hb   = asyncio.create_task(nodeinfo_heartbeat(log), name="task:nodeinfo")

        for t in (t_vma, t_smhi, t_hb):
            watch(t.get_name() or "task", t)

        tasks = [t_vma, t_smhi, t_hb]

        # Graceful shutdown
        stop_evt = asyncio.Event()

        def _stop(*_):
            stop_evt.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _stop)
            except NotImplementedError:
                signal.signal(sig, lambda *_: _stop())

        await stop_evt.wait()

        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        udp_rx.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
