from __future__ import annotations

import asyncio
import logging
import re
from zoneinfo import ZoneInfo
from datetime import datetime
from typing import List

import aiohttp

from ..util import truncate_utf8
from .. import config

log = logging.getLogger(__name__)

INTERVAL = config.SMHI_INTERVAL
URL = config.SMHI_URL
GEOCODE = config.SMHI_GEOCODE
MAX_RETRIES = config.MAX_RETRIES
BASE_BACKOFF = config.BASE_BACKOFF

_STOCKHOLM = ZoneInfo("Europe/Stockholm")

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

    return f"{start_txt} {start_tz} - {end_txt} {end_tz}"


def _to_stockholm(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(_STOCKHOLM)


async def fetch_messages(session: aiohttp.ClientSession) -> List[str]:
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
                    if wa["warningLevel"]["code"] == "MESSAGE":
                        continue

                    if not any(a["id"] == GEOCODE for a in wa["affectedAreas"]):
                        continue

                    start_local = _to_stockholm(datetime.fromisoformat(wa["approximateStart"]))
                    end_local = _to_stockholm(datetime.fromisoformat(wa["approximateEnd"]))
                    time_part = format_range(start_local, end_local)

                    full_message = apply_replacements(
                        f"SMHI: {wa['warningLevel']['sv']} varning {wa['areaName']['sv']} - "
                        f"{wa['eventDescription']['sv']} [{time_part}]"
                    )

                    log.info("[SMHI] New alert %s: %s", alert_id, full_message)
                    out.extend(truncate_utf8(full_message))

            msgs = [m.strip() for m in out if m.strip()]
            log.info("[SMHI] Fetched %d messages", len(msgs))
            for m in msgs:
                log.info("[SMHI] Message: %s", m)

            return msgs

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_exception = e
            if attempt < MAX_RETRIES - 1:
                backoff = BASE_BACKOFF * (2 ** attempt)
                log.warning(
                    "[SMHI] Request failed (attempt %d/%d): %s. Retrying in %ss...",
                    attempt + 1, MAX_RETRIES, e, backoff,
                )
                await asyncio.sleep(backoff)
            else:
                log.error("[SMHI] Request failed after %d attempts: %s", MAX_RETRIES, e)

    log.error("[SMHI] All retry attempts exhausted. Last error: %s", last_exception)
    return []


async def run(session: aiohttp.ClientSession, warmup: bool, push: callable) -> None:
    log.info("[SMHI] Starting source with warmup=%s", warmup)
    msgs = await fetch_messages(session)

    for m in msgs:
        push(m, seen_only=warmup)

    while True:
        await asyncio.sleep(INTERVAL)
        msgs = await fetch_messages(session)
        for m in msgs:
            push(m)