from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Callable, List, Optional

import aiohttp

from ..util import truncate_utf8
from .. import config
from .common import fetch_json_with_retries

log = logging.getLogger(__name__)

INTERVAL = config.VMA_INTERVAL
URL = config.VMA_URL
GEOCODE = config.VMA_GEOCODE
MAX_RETRIES = config.MAX_RETRIES
BASE_BACKOFF = config.BASE_BACKOFF


def _sv_message(alert: dict[str, object]) -> Optional[str]:
    try:
        status: str = alert.get("status") or ""
        msg_type: str = alert.get("msgType") or ""
        sent_iso: Optional[str] = alert.get("sent")

        info = alert.get("info") or alert.get("Info") or []
        i0 = info[0] if isinstance(info, list) and info else {}
        event = i0.get("event") or i0.get("Event") or ""
        description = i0.get("description") or i0.get("Description") or ""

        if status != "Test" and msg_type == "Cancel":
            if sent_iso:
                try:
                    ts = datetime.fromisoformat(sent_iso.replace("Z", "+00:00"))
                    ts_str = ts.strftime("%Y-%m-%d %H:%M")
                except Exception:
                    ts_str = sent_iso
            else:
                ts_str = "tidigare"
            return f"UPPHÄVD: Varningen utfärdad {ts_str} är inte längre aktuell. Faran är över."

        if status == "Exercise" and event == "Kvartalstest av utomhussignal för viktigt meddelande till allmänheten (VMA)":
            return (
                "VMA TEST: Idag kl 15 testas \"Viktigt meddelande\"-signalen - 7s ljud följt av 14s tystnad under 2min. "
                "Efter testet ljuder \"Faran över\" - en 30s lång signal."
            )

        if status == "Exercise":
            return f"ÖVNING: {description}" if description else "ÖVNING: Viktigt meddelande till allmänheten (detaljer saknas)."

        if status == "Actual":
            return f"VMA: {description}" if description else "VMA: Viktigt meddelande till allmänheten (detaljer saknas)."

        return None
    except Exception as exc:
        log.warning("[VMA] Alert parser failed (possible schema drift): %r", exc, exc_info=True)
        return None


async def fetch_messages(session: aiohttp.ClientSession) -> List[str]:
    params = {"geocode": GEOCODE}
    data = await fetch_json_with_retries(
        session,
        URL,
        source_name="VMA",
        log=log,
        params=params,
        max_retries=MAX_RETRIES,
        base_backoff=BASE_BACKOFF,
    )
    if not isinstance(data, dict):
        log.error("[VMA] Payload type invalid: %s", type(data).__name__)
        return []

    out: List[str] = []
    for alert in data.get("alerts") or []:
        if not isinstance(alert, dict):
            continue
        msg = _sv_message(alert)
        if msg:
            out.extend(truncate_utf8(msg))

    msgs = [m.strip() for m in out if m.strip()]
    log.debug("[VMA] Messages fetched: %d", len(msgs))
    for m in msgs:
        log.debug("[VMA] Message ready: %s", m)
    return msgs


async def run(session: aiohttp.ClientSession, warmup: bool, push: Callable[[str, bool], None]) -> None:
    log.info("[VMA] Source started (warmup=%s)", warmup)
    msgs = await fetch_messages(session)

    for m in msgs:
        push(m, seen_only=warmup)

    while True:
        await asyncio.sleep(INTERVAL)
        msgs = await fetch_messages(session)
        for m in msgs:
            push(m, seen_only=False)