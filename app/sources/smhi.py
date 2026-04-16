from __future__ import annotations

import logging
import re
from zoneinfo import ZoneInfo
from datetime import datetime
from typing import Callable

import aiohttp

from ..util import truncate_utf8
from .. import config
from .common import fetch_json_with_retries, run_source

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

_REPL_PATTERN = re.compile(
    "|".join(re.escape(k) for k in sorted(_REPLACEMENTS, key=len, reverse=True)),
    flags=re.IGNORECASE,
)


def apply_replacements(text: str) -> str:
    """Apply direction abbreviations (norra > N, etc.) to text."""
    return _REPL_PATTERN.sub(lambda m: _REPLACEMENTS[m.group(0).casefold()], text)


def format_range(start_local: datetime, end_local: datetime) -> str:
    """Format a time range for display, handling same-day vs multi-day ranges."""
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
    """Convert a datetime to Stockholm timezone."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(_STOCKHOLM)


async def fetch_messages(session: aiohttp.ClientSession) -> list[str]:
    data = await fetch_json_with_retries(
        session,
        URL,
        source_name="SMHI",
        log=log,
        max_retries=MAX_RETRIES,
        base_backoff=BASE_BACKOFF,
    )
    if not isinstance(data, list):
        log.error("[SMHI] Payload type invalid: %s", type(data).__name__)
        return []

    out: list[str] = []
    for alert in data:
        if not isinstance(alert, dict):
            continue
        alert_id = alert.get("id", "unknown")
        warning_areas = alert.get("warningAreas")
        if not isinstance(warning_areas, list):
            continue

        for wa in warning_areas:
            if not isinstance(wa, dict):
                continue
            warning_level = wa.get("warningLevel")
            if not isinstance(warning_level, dict):
                continue
            if warning_level.get("code") == "MESSAGE":
                continue

            affected_areas = wa.get("affectedAreas")
            if not isinstance(affected_areas, list):
                continue
            if not any(isinstance(area, dict) and area.get("id") == GEOCODE for area in affected_areas):
                continue

            start_iso = wa.get("approximateStart")
            end_iso = wa.get("approximateEnd")
            if not isinstance(start_iso, str) or not isinstance(end_iso, str):
                log.warning("[SMHI] Alert skipped (missing time range): %s", alert_id)
                continue

            try:
                start_local = _to_stockholm(datetime.fromisoformat(start_iso))
                end_local = _to_stockholm(datetime.fromisoformat(end_iso))
            except ValueError:
                log.warning("[SMHI] Alert skipped (invalid time range): %s", alert_id)
                continue
            time_part = format_range(start_local, end_local)

            area_name = wa.get("areaName")
            area_name_sv = area_name.get("sv") if isinstance(area_name, dict) else "okänt område"
            event_desc = wa.get("eventDescription")
            event_desc_sv = event_desc.get("sv") if isinstance(event_desc, dict) else "saknar beskrivning"
            level_sv = warning_level.get("sv") or "Okänd"

            full_message = apply_replacements(
                f"SMHI: {level_sv} varning {area_name_sv} - {event_desc_sv} [{time_part}]"
            )

            log.info("[SMHI] Alert accepted: %s (%s)", alert_id, full_message)
            out.extend(truncate_utf8(full_message))

    msgs = [m.strip() for m in out if m.strip()]
    log.debug("[SMHI] Messages fetched: %d", len(msgs))
    for m in msgs:
        log.debug("[SMHI] Message ready: %s", m)

    return msgs


async def run(session: aiohttp.ClientSession, warmup: bool, push: Callable[[str], None]) -> None:
    await run_source(
        source_name="SMHI",
        log=log,
        fetch_messages=lambda: fetch_messages(session),
        push=push,
        interval=INTERVAL,
        warmup=warmup,
    )
