from __future__ import annotations

import asyncio

from redis.asyncio import Redis

_client: Redis | None = None
_lock = asyncio.Lock()


async def get_redis(url: str | None) -> Redis | None:
    if not url:
        return None
    global _client
    if _client is not None:
        return _client
    async with _lock:
        if _client is None:
            _client = Redis.from_url(url, decode_responses=True, health_check_interval=30)
        return _client


async def ping_redis(url: str | None) -> bool:
    client = await get_redis(url)
    if client is None:
        return False
    return bool(await client.ping())


async def close_redis() -> None:
    global _client
    async with _lock:
        client = _client
        _client = None
        if client is not None:
            await client.aclose()
