from __future__ import annotations
import asyncio
import logging
import signal
import sys
from typing import Callable
from collections import deque
from time import monotonic

import aiohttp

from . import config
from . import udp
from .router import Router
from .sources import vma, smhi

MAX_RESTART_INTERVAL = config.MAX_RESTART_INTERVAL
RESTART_HISTORY = config.RESTART_HISTORY

log = logging.getLogger(__name__)

async def supervised_task(
    task_name: str,
    coro_func: Callable,
    log: logging.Logger,
    restart_history: int = RESTART_HISTORY,
    max_interval: int = MAX_RESTART_INTERVAL,
) -> None:
    start_times = deque([float("-inf")], maxlen=restart_history)

    while True:
        start_times.append(monotonic())
        try:
            await coro_func()
            log.info("[ASYNC] Task %s completed normally", task_name)
            break
        except asyncio.CancelledError:
            log.info("[ASYNC] Task %s cancelled", task_name)
            raise
        except Exception as e:
            if min(start_times) > monotonic() - max_interval:
                log.error(
                    "[ASYNC] Task %s failed %d times within %ds — stopping restarts.",
                    task_name, restart_history, max_interval,
                )
                raise
            log.error("[ASYNC] Task %s crashed: %r", task_name, e, exc_info=True)
            log.info("[ASYNC] Restarting task %s in 5 seconds...", task_name)
            await asyncio.sleep(5)


async def nodeinfo_heartbeat(log: logging.Logger) -> None:
    log.info("[Nodeinfo] Broadcast interval started (interval=%ds)", config.MESHTASTIC_NODEINFO_INTERVAL)
    try:
        while True:
            await asyncio.sleep(config.MESHTASTIC_NODEINFO_INTERVAL)
            try:
                udp.send_nodeinfo()
                log.info("[Nodeinfo] Sent")
            except Exception as e:
                log.warning("[Nodeinfo] Send failed: %r", e)
    except asyncio.CancelledError:
        log.info("[Nodeinfo] Broadcast interval stopped")
        raise


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    
    udp.setup_node()
    router = Router(ttl_secs=config.SEEN_TTL_SECS)
    udp.start(on_text=router.mark_seen_from_udp)
    udp.send_nodeinfo()

    async with aiohttp.ClientSession() as session:
        t_vma = asyncio.create_task(
            supervised_task("src:vma", lambda: vma.run(session, warmup=config.WARMUP, push=router.push), log),
            name="src:vma",
        )
        t_smhi = asyncio.create_task(
            supervised_task("src:smhi", lambda: smhi.run(session, warmup=config.WARMUP, push=router.push), log),
            name="src:smhi",
        )
        t_hb = asyncio.create_task(
            supervised_task("task:nodeinfo", lambda: nodeinfo_heartbeat(log), log),
            name="task:nodeinfo",
        )

        tasks = [t_vma, t_smhi, t_hb]

        stop_evt = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: stop_evt.set())
            except NotImplementedError:
                signal.signal(sig, lambda *_: stop_evt.set())

        await stop_evt.wait()

        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        udp.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass