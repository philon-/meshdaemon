from __future__ import annotations

import asyncio
import re
from typing import List

import aiohttp
from datetime import datetime
import pytz

from ..util import truncate_utf8
from .. import config


INTERVAL = config.SMHI_INTERVAL
URL = config.SMHI_URL
GEOCODE = config.SMHI_GEOCODE
MAX_RETRIES = config.MAX_RETRIES
BASE_BACKOFF = config.BASE_BACKOFF

_REPLACEMENTS = {
    "norra": "N",
    "södra": "S",
    "östra": "Ö",
    "västra": "V",

    "nordöstra": "NÖ",
    "nordvästra": "NV",
    "sydöstra": "SÖ",
    "sydvästra": "SV",
}

repl_pattern = re.compile(
    "|".join(re.escape(k) for k in sorted(_REPLACEMENTS, key=len, reverse=True)),
    flags=re.IGNORECASE,
)

def apply_replacements(text: str) -> str:
    return repl_pattern.sub(lambda m: _REPLACEMENTS[m.group(0).casefold()], text)


def format_range(start_local: datetime, end_local: datetime) -> str:
    start_tz = start_local.strftime("%Z")
    end_tz = end_local.strftime("%Z")

    start_txt = start_local.strftime("%d/%m %H:%M")
    if start_local.date() == end_local.date():
        end_txt = end_local.strftime("%H:%M")
    else:
        end_txt = end_local.strftime("%d/%m %H:%M")

    if start_tz == end_tz:
        return f"{start_txt} - {end_txt} {start_tz}"

    # DST boundary (or otherwise differing tzname)
    return f"{start_txt} {start_tz} - {end_txt} {end_tz}"


async def fetch_messages(session: aiohttp.ClientSession, log) -> List[str]:
    last_exception = None

    for attempt in range(MAX_RETRIES):
        try:
            async with session.get(URL, timeout=aiohttp.ClientTimeout(total=15)) as resp:
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
                    if any(a["id"] == GEOCODE for a in wa["affectedAreas"]):

                        stockholm_tz = pytz.timezone("Europe/Stockholm") 

                        # Parse and localize start time
                        start_dt = datetime.fromisoformat(wa["approximateStart"])
                        if start_dt.tzinfo is None:
                            start_dt = pytz.utc.localize(start_dt)
                        start_local = start_dt.astimezone(stockholm_tz) 

                        # Parse and localize end time
                        end_dt = datetime.fromisoformat(wa["approximateEnd"])
                        if end_dt.tzinfo is None:
                            end_dt = pytz.utc.localize(end_dt)
                        end_local = end_dt.astimezone(stockholm_tz)

                        time_part = format_range(start_local, end_local)

                        fullMessage = (
                            f"SMHI: {wa['warningLevel']['sv']} varning {wa['areaName']['sv']} - "
                            f"{wa['eventDescription']['sv']} [{time_part}]"
                        )

                        # Apply NÖ/N/etc replacements (case-insensitive)
                        fullMessage = apply_replacements(fullMessage)

                        log.info(f"[SMHI] New alert {alert_id}: {fullMessage}")

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
                log.warning(
                    f"[SMHI] Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}. "
                    f"Retrying in {backoff_time}s..."
                )
                await asyncio.sleep(backoff_time)
            else:
                log.error(f"[SMHI] Request failed after {MAX_RETRIES} attempts: {e}")

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
