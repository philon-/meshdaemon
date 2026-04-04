from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import List, Optional

import aiohttp

from ..util import truncate_utf8
from .. import config

log = logging.getLogger(__name__)

INTERVAL = config.VMA_INTERVAL
URL = config.VMA_URL
GEOCODE = config.VMA_GEOCODE
MAX_RETRIES = config.MAX_RETRIES
BASE_BACKOFF = config.BASE_BACKOFF


def _sv_message(alert: dict) -> Optional[str]:
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
    except Exception:
        return None


async def fetch_messages(session: aiohttp.ClientSession) -> List[str]:
    params = {"geocode": GEOCODE}
    last_exception = None

    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(URL, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                resp.raise_for_status()
                data = await resp.json()

            out: List[str] = []
            for alert in data.get("alerts") or []:
                if not isinstance(alert, dict):
                    continue
                msg = _sv_message(alert)
                if msg:
                    out.extend(truncate_utf8(msg))

            msgs = [m.strip() for m in out if m.strip()]
            log.info("[VMA] Fetched %d messages", len(msgs))
            for m in msgs:
                log.info("[VMA] Message: %s", m)
            return msgs

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_exception = e
            if attempt < MAX_RETRIES - 1:
                backoff = BASE_BACKOFF * (2 ** attempt)
                log.warning(
                    "[VMA] Request failed (attempt %d/%d): %s. Retrying in %ss...",
                    attempt + 1, MAX_RETRIES, e, backoff,
                )
                await asyncio.sleep(backoff)
            else:
                log.error("[VMA] Request failed after %d attempts: %s", MAX_RETRIES, e)

    log.error("[VMA] All retry attempts exhausted. Last error: %s", last_exception)
    return []


async def run(session: aiohttp.ClientSession, warmup: bool, push: callable) -> None:
    log.info("[VMA] Starting source with warmup=%s", warmup)
    msgs = await fetch_messages(session)

    for m in msgs:
        push(m, seen_only=warmup)

    while True:
        await asyncio.sleep(INTERVAL)
        msgs = await fetch_messages(session)
        for m in msgs:
            push(m)