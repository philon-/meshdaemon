from __future__ import annotations
import asyncio
import logging
import signal
import sys
from typing import Awaitable, Callable
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
    coro_func: Callable[[], Awaitable[None]],
    log: logging.Logger,
    restart_history: int = RESTART_HISTORY,
    max_interval: int = MAX_RESTART_INTERVAL,
) -> None:
    start_times = deque(maxlen=restart_history)

    while True:
        start_times.append(monotonic())
        try:
            await coro_func()
            log.info("[ASYNC] Task completed: %s", task_name)
            break
        except asyncio.CancelledError:
            log.info("[ASYNC] Task cancelled: %s", task_name)
            raise
        except Exception as exc:
            now = monotonic()
            restarts_in_window = sum(1 for ts in start_times if now - ts <= max_interval)
            if restarts_in_window >= restart_history:
                log.error(
                    "[ASYNC] Task restart limit reached: %s (%d failures in %ds)",
                    task_name, restart_history, max_interval,
                )
                raise
            log.error("[ASYNC] Task crashed: %s (%r)", task_name, exc, exc_info=True)
            log.info("[ASYNC] Task restart scheduled in 5s: %s", task_name)
            await asyncio.sleep(5)


async def nodeinfo_heartbeat(log: logging.Logger) -> None:
    log.info("[NODEINFO] Heartbeat started (interval=%ds)", config.MESHTASTIC_NODEINFO_INTERVAL)
    try:
        while True:
            await asyncio.sleep(config.MESHTASTIC_NODEINFO_INTERVAL)
            try:
                udp.send_nodeinfo()
                log.info("[NODEINFO] Packet sent")
            except Exception as exc:
                log.warning("[NODEINFO] Packet send failed: %r", exc)
    except asyncio.CancelledError:
        log.info("[NODEINFO] Heartbeat stopped")
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

        stop_waiter = asyncio.create_task(stop_evt.wait(), name="task:stop-waiter")
        done, _ = await asyncio.wait([*tasks, stop_waiter], return_when=asyncio.FIRST_COMPLETED)

        if stop_waiter not in done:
            for completed in done:
                if completed.cancelled():
                    continue
                exc = completed.exception()
                if exc is None:
                    log.error("[ASYNC] Task exited unexpectedly: %s", completed.get_name())
                else:
                    log.error("[ASYNC] Task failed: %s (%r)", completed.get_name(), exc)
            stop_evt.set()

        for t in tasks:
            t.cancel()
        stop_waiter.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(stop_waiter, return_exceptions=True)

        udp.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass