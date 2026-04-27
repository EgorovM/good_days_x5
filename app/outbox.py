from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Protocol

from redis.asyncio import Redis

from app.game_engine import Segment
from app.serialization import segments_from_dicts, segments_to_dicts


@dataclass
class OutboxTask:
    platform: str  # tg | vk
    recipient_id: int
    segments: list[Segment]
    dedupe_key: str
    attempt: int = 0
    meta: dict[str, Any] | None = None


class Outbox(Protocol):
    async def enqueue(self, task: OutboxTask) -> bool: ...

    async def queue_size(self) -> int: ...

    async def ready(self) -> bool: ...


def task_to_json(task: OutboxTask) -> str:
    return json.dumps(
        {
            "platform": task.platform,
            "recipient_id": task.recipient_id,
            "segments": segments_to_dicts(task.segments),
            "dedupe_key": task.dedupe_key,
            "attempt": task.attempt,
            "meta": task.meta or {},
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def task_from_json(raw: str) -> OutboxTask:
    data = json.loads(raw)
    return OutboxTask(
        platform=str(data["platform"]),
        recipient_id=int(data["recipient_id"]),
        segments=segments_from_dicts(data["segments"]),
        dedupe_key=str(data["dedupe_key"]),
        attempt=int(data.get("attempt") or 0),
        meta=data.get("meta") if isinstance(data.get("meta"), dict) else {},
    )


class MemoryOutbox:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[OutboxTask] = asyncio.Queue()
        self._dedupe: dict[str, float] = {}

    async def enqueue(self, task: OutboxTask) -> bool:
        now = time.monotonic()
        # Простая уборка старых ключей, чтобы локальный fallback не рос бесконечно.
        if len(self._dedupe) > 10_000:
            cutoff = now - 86_400
            self._dedupe = {k: v for k, v in self._dedupe.items() if v > cutoff}
        if task.dedupe_key in self._dedupe:
            return False
        self._dedupe[task.dedupe_key] = now
        await self.queue.put(task)
        return True

    async def get(self) -> OutboxTask:
        return await self.queue.get()

    def done(self) -> None:
        self.queue.task_done()

    async def queue_size(self) -> int:
        return self.queue.qsize()

    async def ready(self) -> bool:
        return True


class RedisOutbox:
    def __init__(
        self,
        redis: Redis,
        *,
        stream: str = "good_days:outbox",
        dedupe_prefix: str = "good_days:dedupe",
        dedupe_ttl_seconds: int = 86_400,
    ) -> None:
        self.redis = redis
        self.stream = stream
        self.dedupe_prefix = dedupe_prefix
        self.dedupe_ttl_seconds = dedupe_ttl_seconds

    async def enqueue(self, task: OutboxTask) -> bool:
        dedupe_key = f"{self.dedupe_prefix}:{task.dedupe_key}"
        is_new = await self.redis.set(dedupe_key, "1", nx=True, ex=self.dedupe_ttl_seconds)
        if not is_new:
            return False
        await self.redis.xadd(self.stream, {"payload": task_to_json(task)}, maxlen=100_000, approximate=True)
        return True

    async def queue_size(self) -> int:
        return int(await self.redis.xlen(self.stream))

    async def ready(self) -> bool:
        return bool(await self.redis.ping())
