# Documentation example (aiohttp, Client Quickstart > Timeouts): timeout = aiohttp.ClientTimeout(total=60);
# async with aiohttp.ClientSession(timeout=timeout) as session, placed in the minimal R1 function of the D61 check.
import asyncio

import aiohttp


class ProfileError(Exception):
    pass


async def _get(url):
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise ProfileError(f"status {resp.status}")
            return await resp.json()


def get_user_profile(base_url: str, user_id: str) -> dict:
    url = f"{base_url.rstrip('/')}/v1/users/{user_id}"
    try:
        return asyncio.run(_get(url))
    except ProfileError:
        raise
    except (aiohttp.ClientError, asyncio.TimeoutError) as e:
        raise ProfileError(str(e)) from e
