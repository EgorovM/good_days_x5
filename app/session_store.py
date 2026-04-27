from __future__ import annotations

import json
from dataclasses import asdict
from typing import Protocol

from redis.asyncio import Redis

from app.game_engine import GameSession


class SessionStore(Protocol):
    async def get(self, platform: str, user_id: int) -> GameSession | None: ...

    async def set(self, platform: str, user_id: int, session: GameSession) -> None: ...

    async def delete(self, platform: str, user_id: int) -> None: ...

    async def ready(self) -> bool: ...


class MemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, GameSession] = {}

    def _key(self, platform: str, user_id: int) -> str:
        return f"{platform}:{user_id}"

    async def get(self, platform: str, user_id: int) -> GameSession | None:
        return self._sessions.get(self._key(platform, user_id))

    async def set(self, platform: str, user_id: int, session: GameSession) -> None:
        self._sessions[self._key(platform, user_id)] = session

    async def delete(self, platform: str, user_id: int) -> None:
        self._sessions.pop(self._key(platform, user_id), None)

    async def ready(self) -> bool:
        return True


class RedisSessionStore:
    def __init__(self, redis: Redis, *, ttl_seconds: int = 86_400, prefix: str = "good_days:sess") -> None:
        self.redis = redis
        self.ttl_seconds = ttl_seconds
        self.prefix = prefix

    def _key(self, platform: str, user_id: int) -> str:
        return f"{self.prefix}:{platform}:{user_id}"

    async def get(self, platform: str, user_id: int) -> GameSession | None:
        raw = await self.redis.get(self._key(platform, user_id))
        if not raw:
            return None
        data = json.loads(raw)
        return GameSession(**data)

    async def set(self, platform: str, user_id: int, session: GameSession) -> None:
        await self.redis.set(self._key(platform, user_id), json.dumps(asdict(session)), ex=self.ttl_seconds)

    async def delete(self, platform: str, user_id: int) -> None:
        await self.redis.delete(self._key(platform, user_id))

    async def ready(self) -> bool:
        return bool(await self.redis.ping())
