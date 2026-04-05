from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp


async def fetch_json_with_retries(
    session: aiohttp.ClientSession,
    url: str,
    *,
    source_name: str,
    log: logging.Logger,
    params: dict[str, Any] | None = None,
    max_retries: int,
    base_backoff: int,
    timeout_total: int = 15,
) -> Any | None:
    last_exception: Exception | None = None

    for attempt in range(max_retries):
        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=timeout_total)) as resp:
                resp.raise_for_status()
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            last_exception = exc
            if attempt < max_retries - 1:
                backoff = base_backoff * (2 ** attempt)
                log.warning(
                    "[%s] Request failed (attempt %d/%d): %s; retrying in %ss",
                    source_name,
                    attempt + 1,
                    max_retries,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
            else:
                log.error("[%s] Request failed after %d attempts: %s", source_name, max_retries, exc)

    log.error("[%s] All retry attempts exhausted. Last error: %s", source_name, last_exception)
    return None