from __future__ import annotations

from app import runtime
from app.config import Settings
from app.media_cache import MemoryMediaCache, RedisMediaCache
from app.outbox import MemoryOutbox, RedisOutbox
from app.redis_client import get_redis
from app.session_store import MemorySessionStore, RedisSessionStore


async def configure_runtime(settings: Settings) -> None:
    runtime.settings = settings
    redis = await get_redis(settings.redis_url)
    if redis is None:
        runtime.session_store = MemorySessionStore()
        runtime.outbox = MemoryOutbox()
        runtime.media_cache = MemoryMediaCache()
        return
    runtime.session_store = RedisSessionStore(redis, ttl_seconds=settings.session_ttl_seconds)
    runtime.outbox = RedisOutbox(redis)
    runtime.media_cache = RedisMediaCache(redis)
