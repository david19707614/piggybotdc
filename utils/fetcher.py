import aiohttp
import json
import os

API_URL = ""
TEST_FILE = "data/test-assets.json"

async def load_assets(test_mode: bool = False) -> dict:
    """
    Returns a dict keyed by asset_ticker.
    In test mode the JSON file is read locally.
    """
    if test_mode:
        with open(TEST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        async with aiohttp.ClientSession() as session:
            async with session.get(API_URL) as resp:
                data = await resp.json()

    # Normalise: ensure every entry has an `asset_ticker`
    return {item["asset_ticker"]: item for item in data if "asset_ticker" in item}