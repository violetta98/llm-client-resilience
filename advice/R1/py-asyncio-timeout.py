# Advice check (D52, message revised D56): asyncio.timeout (Python 3.11+) around an asynchronous HTTPX client.
import asyncio

import httpx


class ProfileError(Exception):
    pass


async def _get(url: str) -> dict:
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=2.0)) as c:
        async with asyncio.timeout(10.0):
            r = await c.get(url)
        if r.status_code != 200:
            raise ProfileError(f"status {r.status_code}")
        return r.json()


def get_user_profile(base_url: str, user_id: str) -> dict:
    try:
        return asyncio.run(_get(f"{base_url.rstrip('/')}/v1/users/{user_id}"))
    except TimeoutError as e:
        raise ProfileError("deadline exceeded") from e
    except (httpx.HTTPError, ValueError) as e:
        raise ProfileError(str(e)) from e
