# Baseline: aiohttp, all defaults (GET).
import aiohttp

async def get_user_profile(base_url: str, user_id: str) -> dict:
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{base_url}/v1/users/{user_id}") as r:
            r.raise_for_status()
            return await r.json()
