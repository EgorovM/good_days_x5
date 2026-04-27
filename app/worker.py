from __future__ import annotations

import asyncio
import logging
import time
from contextlib import suppress

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramUnauthorizedError
from redis.exceptions import ResponseError

from app import runtime, vk_client
from app.config import get_settings
from app.metrics import QUEUE_SIZE, RETRY_EVENTS, SEND_EVENTS, SEND_LATENCY
from app.outbox import MemoryOutbox, OutboxTask, RedisOutbox, task_from_json, task_to_json
from app.redis_client import close_redis
from app.services import configure_runtime
from app.telegram_delivery import send_telegram_segments
from app.vk_delivery import send_vk_segments

log = logging.getLogger(__name__)

PERMANENT_TG_ERRORS = (TelegramBadRequest, TelegramForbiddenError, TelegramUnauthorizedError)


def _retry_delay(attempt: int) -> float:
    return min(30.0, 0.5 * (2**attempt))


async def send_outbox_task(task: OutboxTask, *, tg_bot: Bot | None) -> None:
    start = time.monotonic()
    try:
        if runtime.settings and runtime.settings.dry_run_delivery:
            log.info(
                "dry_run delivery platform=%s recipient=%s segments=%s",
                task.platform,
                task.recipient_id,
                len(task.segments),
            )
            SEND_EVENTS.labels(task.platform, "dry_run").inc()
            return
        if task.platform == "tg":
            if tg_bot is None:
                raise RuntimeError("Telegram is not configured")
            await send_telegram_segments(tg_bot, task.recipient_id, task.segments)
        elif task.platform == "vk":
            settings = runtime.settings
            if settings is None or not settings.has_vk:
                raise RuntimeError("VK is not configured")
            await send_vk_segments(
                token=settings.vk_api_token or "",
                group_id=abs(int(settings.vk_group_id or 0)),
                peer_id=task.recipient_id,
                segments=task.segments,
            )
        else:
            raise RuntimeError(f"Unknown outbox platform {task.platform!r}")
        SEND_EVENTS.labels(task.platform, "ok").inc()
    except Exception:
        SEND_EVENTS.labels(task.platform, "error").inc()
        raise
    finally:
        SEND_LATENCY.labels(task.platform).observe(time.monotonic() - start)


async def _requeue_after_delay(task: OutboxTask, delay: float) -> None:
    await asyncio.sleep(delay)
    task.attempt += 1
    RETRY_EVENTS.labels(task.platform).inc()
    outbox = runtime.outbox
    if isinstance(outbox, MemoryOutbox):
        await outbox.queue.put(task)
    elif isinstance(outbox, RedisOutbox):
        await outbox.redis.xadd(outbox.stream, {"payload": task_to_json(task)}, maxlen=100_000, approximate=True)


def _is_permanent_error(exc: BaseException) -> bool:
    return isinstance(exc, PERMANENT_TG_ERRORS)


async def _handle_task(task: OutboxTask, *, tg_bot: Bot | None) -> None:
    settings = runtime.settings
    max_attempts = settings.outbox_max_attempts if settings else 4
    try:
        await send_outbox_task(task, tg_bot=tg_bot)
    except Exception as exc:
        if _is_permanent_error(exc) or task.attempt + 1 >= max_attempts:
            log.exception(
                "outbox task failed permanently platform=%s recipient=%s attempt=%s",
                task.platform,
                task.recipient_id,
                task.attempt,
            )
            return
        delay = _retry_delay(task.attempt)
        log.warning(
            "outbox task failed, retrying platform=%s recipient=%s attempt=%s delay=%.1fs error=%r",
            task.platform,
            task.recipient_id,
            task.attempt,
            delay,
            exc,
        )
        await _requeue_after_delay(task, delay)


async def run_memory_worker(*, tg_bot: Bot | None, stop_event: asyncio.Event | None = None) -> None:
    outbox = runtime.outbox
    if not isinstance(outbox, MemoryOutbox):
        return
    while stop_event is None or not stop_event.is_set():
        task = await outbox.get()
        try:
            await _handle_task(task, tg_bot=tg_bot)
        finally:
            outbox.done()
            QUEUE_SIZE.set(await outbox.queue_size())


async def _ensure_group(outbox: RedisOutbox, group: str) -> None:
    try:
        await outbox.redis.xgroup_create(outbox.stream, group, id="0", mkstream=True)
    except ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def run_redis_worker(
    *,
    tg_bot: Bot | None,
    group: str = "senders",
    consumer: str = "worker-1",
    stop_event: asyncio.Event | None = None,
) -> None:
    outbox = runtime.outbox
    if not isinstance(outbox, RedisOutbox):
        return
    await _ensure_group(outbox, group)
    sem = asyncio.Semaphore(runtime.settings.worker_concurrency if runtime.settings else 24)

    async def process(message_id: str, payload: str) -> None:
        async with sem:
            try:
                await _handle_task(task_from_json(payload), tg_bot=tg_bot)
            finally:
                await outbox.redis.xack(outbox.stream, group, message_id)
                await outbox.redis.xdel(outbox.stream, message_id)
                QUEUE_SIZE.set(await outbox.queue_size())

    while stop_event is None or not stop_event.is_set():
        reclaimed = []
        try:
            _next_id, reclaimed, _deleted = await outbox.redis.xautoclaim(
                outbox.stream,
                group,
                consumer,
                min_idle_time=60_000,
                start_id="0-0",
                count=runtime.settings.worker_concurrency if runtime.settings else 24,
            )
        except ResponseError:
            reclaimed = []
        if reclaimed:
            tasks = []
            for message_id, fields in reclaimed:
                payload = fields.get("payload")
                if payload:
                    tasks.append(asyncio.create_task(process(message_id, payload)))
            if tasks:
                await asyncio.gather(*tasks)
            continue
        rows = await outbox.redis.xreadgroup(
            group,
            consumer,
            streams={outbox.stream: ">"},
            count=runtime.settings.worker_concurrency if runtime.settings else 24,
            block=5000,
        )
        for _stream, messages in rows:
            tasks = []
            for message_id, fields in messages:
                payload = fields.get("payload")
                if payload:
                    tasks.append(asyncio.create_task(process(message_id, payload)))
            if tasks:
                await asyncio.gather(*tasks)


async def run_worker_forever() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    await configure_runtime(settings)
    tg_bot: Bot | None = None
    if settings.has_telegram:
        tg_bot = Bot(
            settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            session=AiohttpSession(limit=250, timeout=35.0),
        )
    try:
        if isinstance(runtime.outbox, RedisOutbox):
            await run_redis_worker(tg_bot=tg_bot)
        else:
            await run_memory_worker(tg_bot=tg_bot)
    finally:
        if tg_bot is not None:
            await tg_bot.session.close()
        await vk_client.aclose_http_client()
        await close_redis()


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        asyncio.run(run_worker_forever())
