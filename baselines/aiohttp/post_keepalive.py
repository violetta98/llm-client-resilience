# Baseline: aiohttp, all defaults (POST on a reused keep-alive connection, S8 variant, D42).
# A ClientSession is bound to an event loop and the driver runs each call in its
# own asyncio.run(), so the shared session is kept per loop (created once per loop).
import asyncio

import aiohttp

_sessions: dict = {}

async def send_sms(base_url: str, to: str, body: str) -> str:
    loop = asyncio.get_running_loop()
    s = _sessions.get(loop) or _sessions.setdefault(loop, aiohttp.ClientSession())
    async with s.get(f"{base_url}/v1/messages") as g:  # warm the pool; 405 ignored
        await g.read()  # body read so the connection is released idle
    async with s.post(f"{base_url}/v1/messages", json={"to": to, "body": body}) as r:
        r.raise_for_status()
        return (await r.json())["id"]
