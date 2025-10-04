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
MAX_RETRIES = config.MAX_RETRIES
BASE_BACKOFF = config.BASE_BACKOFF

async def fetch_messages(session: aiohttp.ClientSession, log) -> List[str]:
    last_exception = None
    
    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                resp.raise_for_status()
                data = await resp.json()
            
            # Success - process the data
            out: List[str] = []
            for alert in data:
                alert_id = alert["id"]

                for wa in alert["warningAreas"]:
                    # Filter out MESSAGEs
                    if wa["warningLevel"]["code"] == "MESSAGE":
                        continue

                    # Check if warningArea affects area with id=GEOCODE
                    if any(a["id"] == GEOCODE for a in wa["affectedAreas"]):
                        # Construct the full message
                        fullMessage = f"SMHI: {wa['warningLevel']['sv']} varning för {wa['areaName']['sv']} - {wa['eventDescription']['sv']} från {datetime.fromisoformat(wa['approximateStart']).strftime('%Y-%m-%d %H:%M')} till {datetime.fromisoformat(wa['approximateEnd']).strftime('%Y-%m-%d %H:%M')}"
                        
                        log.info(f"[SMHI] New alert {alert_id}")

                        # Cut it up if it's too long
                        messages = truncate_utf8(fullMessage)
                        out.extend(messages)
            
            msgs = [m.strip() for m in out if m.strip()]

            log.info(f"[SMHI] Fetched {len(msgs)} messages")
            for m in msgs:
                log.info(f"[SMHI] Message: {m}")
                
            return msgs
            
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_exception = e
            if attempt < MAX_RETRIES - 1:
                backoff_time = BASE_BACKOFF * (2 ** attempt)
                log.warning(f"[SMHI] Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}. Retrying in {backoff_time}s...")
                await asyncio.sleep(backoff_time)
            else:
                log.error(f"[SMHI] Request failed after {MAX_RETRIES} attempts: {e}")
    
    # If all retries failed, return empty list
    log.error(f"[SMHI] All retry attempts exhausted. Last error: {last_exception}")
    return []

async def run(session: aiohttp.ClientSession, log, warmup: bool, push: callable) -> None:
    log.info("[SMHI] Starting source with warmup=%s", warmup)
    msgs = await fetch_messages(session, log)

    for m in msgs:
        push(m, seen_only=warmup)
    
    while True:
        await asyncio.sleep(INTERVAL)
        msgs = await fetch_messages(session, log)
        for m in msgs:
            push(m)
