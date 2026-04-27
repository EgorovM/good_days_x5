from __future__ import annotations

from pathlib import Path
from typing import Protocol

from redis.asyncio import Redis


class MediaCache(Protocol):
    async def get(self, platform: str, filename: str, stamp: str) -> str | None: ...

    async def set(self, platform: str, filename: str, stamp: str, value: str) -> None: ...

    async def ready(self) -> bool: ...


def media_stamp(path: Path) -> str:
    st = path.stat()
    return f"{int(st.st_mtime)}:{st.st_size}"


class MemoryMediaCache:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def _key(self, platform: str, filename: str, stamp: str) -> str:
        return f"{platform}:{filename}:{stamp}"

    async def get(self, platform: str, filename: str, stamp: str) -> str | None:
        return self._data.get(self._key(platform, filename, stamp))

    async def set(self, platform: str, filename: str, stamp: str, value: str) -> None:
        self._data[self._key(platform, filename, stamp)] = value

    async def ready(self) -> bool:
        return True


class RedisMediaCache:
    def __init__(self, redis: Redis, *, prefix: str = "good_days:media", ttl_seconds: int = 30 * 86_400) -> None:
        self.redis = redis
        self.prefix = prefix
        self.ttl_seconds = ttl_seconds

    def _key(self, platform: str, filename: str, stamp: str) -> str:
        return f"{self.prefix}:{platform}:{filename}:{stamp}"

    async def get(self, platform: str, filename: str, stamp: str) -> str | None:
        return await self.redis.get(self._key(platform, filename, stamp))

    async def set(self, platform: str, filename: str, stamp: str, value: str) -> None:
        await self.redis.set(self._key(platform, filename, stamp), value, ex=self.ttl_seconds)

    async def ready(self) -> bool:
        return bool(await self.redis.ping())
