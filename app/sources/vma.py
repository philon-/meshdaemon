from __future__ import annotations
import asyncio
from typing import List, Optional
import aiohttp
from datetime import datetime

from ..util import truncate_utf8
from .. import config

INTERVAL = config.VMA_INTERVAL  
URL = config.VMA_URL             
GEOCODE = config.VMA_GEOCODE
LOG_VERBOSE = config.LOG_VERBOSE

def _sv_message(alert: dict) -> Optional[str]:
    try:
        status: str = alert.get("status") or ""
        msg_type: str = alert.get("msgType") or ""
        sent_iso: Optional[str] = alert.get("sent")

        info = alert.get("info") or alert.get("Info") or []
        i0 = info[0] if isinstance(info, list) and info else {}
        event = i0.get("event") or i0.get("Event") or ""
        description = i0.get("description") or i0.get("Description") or ""

        # Cancel (and not a Test)
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

        # Quarterly siren test (special phrasing)
        if status == "Exercise" and event == "Kvartalstest av utomhussignal för viktigt meddelande till allmänheten (VMA)":
            return (
                "VMA TEST: Idag kl 15 testas “Viktigt meddelande”-signalen - 7s ljud följt av 14s tystnad under 2min. "
                "Efter testet ljuder “Faran över” - en 30s lång signal."
            )

        # Generic exercise
        if status == "Exercise":
            return f"ÖVNING: {description}" if description else "ÖVNING: Viktigt meddelande till allmänheten (detaljer saknas)."

        # Actual alert
        if status == "Actual":
            return f"VMA: {description}" if description else "VMA: Viktigt meddelande till allmänheten (detaljer saknas)."

        return None
    except Exception:
        return None


async def fetch_messages(session: aiohttp.ClientSession, log) -> List[str]:
    params = {"geocode": GEOCODE}
    async with session.get(URL, params=params, timeout=15) as resp:
        resp.raise_for_status()
        data = await resp.json()

    items = data.get("alerts")
    out: List[str] = []
    
    for alert in items:
        
        if not isinstance(alert, dict):
            continue

        msg = _sv_message(alert)
        if not msg:
            continue

        parts = truncate_utf8(msg)
        out.extend(parts)
    msgs = [m.strip() for m in out if m and m.strip()]
    if LOG_VERBOSE:
        log.info(f"[VMA] Fetched {len(msgs)} messages")
        for m in msgs:
            log.info(f"[VMA] Message: {m}")
    return msgs


async def run(session: aiohttp.ClientSession, log, warmup: bool, push: callable) -> None:
    log.info("[VMA] Starting source with warmup=%s", warmup)
    msgs = await fetch_messages(session, log)

    for m in msgs:
        push(m, seen_only=warmup)

    while True:
        await asyncio.sleep(INTERVAL)
        msgs = await fetch_messages(session, log)
        for m in msgs:
            push(m)
