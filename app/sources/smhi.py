from __future__ import annotations
import asyncio
from typing import Iterable, List
import aiohttp
from datetime import datetime

from ..util import truncate_utf8
from .. import config

INTERVAL = config.SMHI_INTERVAL
URL = config.SMHI_URL
GEOCODE = config.SMHI_GEOCODE

async def fetch_messages(session: aiohttp.ClientSession, log) -> List[str]:
    async with session.get(URL, timeout=15) as resp:
        resp.raise_for_status()
        data = await resp.json()

    out: List[str] = []
    for alert in data:
        alert_id = alert["id"]

        for wa in alert["warningAreas"]:
            # Filter out MESSAGEs
            if wa["warningLevel"]["code"] == "MESSAGE":
                continue

            # Check if warningArea affects area with id=GEOCODE
            if any(a["id"] == GEOCODE for a in wa["affectedAreas"]) :
                # Construct the full message
                fullMessage = f"SMHI: {wa['warningLevel']['sv']} varning för {wa['areaName']['sv']} - {wa['eventDescription']['sv']} från {datetime.fromisoformat(wa['approximateStart']).strftime('%Y-%m-%d %H:%M')} till {datetime.fromisoformat(wa['approximateEnd']).strftime('%Y-%m-%d %H:%M')}"
                
                log.info(f"[SMHI] New alert {alert_id}")

                # Cut it up if it's too long
                messages = truncate_utf8(fullMessage)

                out.extend(messages)
    
    return [m.strip() for m in out if m.strip()]

async def run(session: aiohttp.ClientSession, log, warmup: bool, push: callable) -> None:
    log.info("[SMHI] Starting source with warmup=%s", warmup)
    msgs = await fetch_messages(session, log)
    if warmup:
        for m in msgs:
            push(m, seen_only=True)
    
    while True:
        await asyncio.sleep(INTERVAL)
        msgs = await fetch_messages(session, log)
        for m in msgs:
            push(m)
