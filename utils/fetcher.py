import asyncio
import json
import os

import aiohttp
from loguru import logger

API_URL = "https://app.piggybank.fi/api/v0/static/assets"
TEST_FILE = "data/test-assets.json"


class FetchError(Exception):
    """Raised when asset data cannot be fetched."""


async def load_assets(*, test_mode: bool = False,
                      session: aiohttp.ClientSession | None = None) -> dict:
    """
    Returns a dict keyed by asset_ticker.
    In test mode the JSON file is read locally.
    In live mode an existing *session* must be provided.
    """
    if test_mode:
        with open(TEST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        if session is None:
            raise FetchError("An aiohttp.ClientSession is required in live mode")

        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with session.get(API_URL, timeout=timeout) as resp:
                if resp.status != 200:
                    raise FetchError(f"HTTP {resp.status} from PiggyBank API")
                try:
                    data = await resp.json()
                except (json.JSONDecodeError, aiohttp.ContentTypeError) as exc:
                    raise FetchError(f"Invalid JSON from PiggyBank API: {exc}") from exc
        except asyncio.TimeoutError as exc:
            raise FetchError("Request to PiggyBank API timed out (15s)") from exc

    return {item["asset_ticker"]: item for item in data if "asset_ticker" in item}


async def load_assets_with_retry(*, test_mode: bool = False,
                                 session: aiohttp.ClientSession | None = None,
                                 attempts: int = 3) -> dict:
    """Wrapper around load_assets with exponential back-off (1s, 2s, 4s)."""
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await load_assets(test_mode=test_mode, session=session)
        except FetchError as exc:
            last_exc = exc
            if attempt < attempts:
                wait = 2 ** (attempt - 1)  # 1, 2, 4
                logger.warning("Fetch attempt {}/{} failed ({}), retrying in {}s",
                               attempt, attempts, exc, wait)
                await asyncio.sleep(wait)

    logger.error("All {} fetch attempts failed: {}", attempts, last_exc)
    raise last_exc  # type: ignore[misc]
