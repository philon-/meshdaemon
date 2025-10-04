from __future__ import annotations
import asyncio
import logging
import signal
import sys
from typing import Callable
import time
import aiohttp
from collections import deque
from time import monotonic

from . import config
from .udp import setup_node, PubSubReceiver, send_nodeinfo
from .router import Router

# Sources
from .sources import vma, smhi

# Supervisor configuration
MAX_RESTART_INTERVAL = config.MAX_RESTART_INTERVAL
RESTART_HISTORY = config.RESTART_HISTORY

async def supervised_task(task_name: str, coro_func: Callable, log: logging.Logger, 
                          restart_history: int = RESTART_HISTORY, 
                          max_interval: int = MAX_RESTART_INTERVAL) -> None:

    start_times = deque([float('-inf')], maxlen=restart_history)
    
    while True:
        start_times.append(monotonic())
        try:
            await coro_func()
            # If the coroutine returns normally, break the restart loop
            log.info(f"[ASYNC] Task {task_name} completed normally")
            break
        except asyncio.CancelledError:
            log.info(f"[ASYNC] Task {task_name} cancelled")
            raise
        except Exception as e:
            # Check if we're in a restart loop
            if min(start_times) > monotonic() - max_interval:
                log.error(
                    f"[ASYNC] Task {task_name} failed {restart_history} times within {max_interval}s. "
                    "[ASYNC] Stopping restart attempts to prevent restart loop."
                )
                raise
            else:
                log.error(f"[ASYNC] Task {task_name} crashed: {e!r}", exc_info=True)
                log.info(f"[ASYNC] Restarting task {task_name} in 5 seconds...")
                await asyncio.sleep(5)

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

    router = Router(ttl_secs=config.SEEN_TTL_SECS, log=log, hold_window=config.HOLD_WINDOW_SECS, 
                    node_id=config.MESHTASTIC_NODE_ID, salt=config.INSTANCE_SALT)

    # UDP RX to mark seen
    udp_rx = PubSubReceiver(log, on_text=router.mark_seen_from_udp)
    udp_rx.start()

    async with aiohttp.ClientSession() as session:
        # Create supervised tasks that will auto-restart on failure
        # Pass router.push directly to the sources
        t_vma = asyncio.create_task(
            supervised_task("src:vma", 
                          lambda: vma.run(session, log, warmup=config.WARMUP, push=router.push), 
                          log),
            name="src:vma"
        )
        t_smhi = asyncio.create_task(
            supervised_task("src:smhi", 
                          lambda: smhi.run(session, log, warmup=config.WARMUP, push=router.push), 
                          log),
            name="src:smhi"
        )
        t_hb = asyncio.create_task(
            supervised_task("task:nodeinfo", 
                          lambda: nodeinfo_heartbeat(log), 
                          log),
            name="task:nodeinfo"
        )

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
