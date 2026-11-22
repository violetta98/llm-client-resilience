# Baseline: aiohttp, all defaults (POST).
import aiohttp

async def send_sms(base_url: str, to: str, body: str) -> str:
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{base_url}/v1/messages", json={"to": to, "body": body}) as r:
            r.raise_for_status()
            return (await r.json())["id"]
