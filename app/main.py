from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.types import Update
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app import runtime
from app import vk_client
from app.metrics import WEBHOOK_EVENTS, WEBHOOK_LATENCY, metrics_response
from app.outbox import MemoryOutbox
from app.redis_client import close_redis
from app.services import configure_runtime
from app.telegram_bot import build_tg_dispatcher
from app.vk_router import build_vk_router
from app.worker import run_memory_worker

settings = get_settings()
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await configure_runtime(settings)
    app.state.worker_stop = asyncio.Event()
    app.state.memory_worker_task = None
    if settings.has_telegram:
        tg_session = AiohttpSession(limit=250, timeout=35.0)
        app.state.tg_bot = Bot(
            settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            session=tg_session,
        )
        app.state.tg_dp = build_tg_dispatcher()
    if isinstance(runtime.outbox, MemoryOutbox):
        app.state.memory_worker_task = asyncio.create_task(
            run_memory_worker(tg_bot=getattr(app.state, "tg_bot", None), stop_event=app.state.worker_stop)
        )
    yield
    app.state.worker_stop.set()
    if getattr(app.state, "memory_worker_task", None):
        app.state.memory_worker_task.cancel()
    if getattr(app.state, "tg_bot", None):
        await app.state.tg_bot.session.close()
    await vk_client.aclose_http_client()
    await close_redis()


app = FastAPI(title="X5 Good Days bot", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(build_vk_router(settings))


@app.middleware("http")
async def request_log_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    started = time.monotonic()
    response = await call_next(request)
    latency_ms = int((time.monotonic() - started) * 1000)
    log.info(
        "request_done request_id=%s method=%s path=%s status=%s latency_ms=%s",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        latency_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/vk/miniapp", response_class=HTMLResponse)
async def vk_miniapp_page() -> HTMLResponse:
    """Статическая страница для VK Mini App: кнопка открывает чат с сообществом (настройте URL приложения в кабинете VK)."""
    gid = abs(int(settings.vk_group_id or 0))
    path = Path(__file__).resolve().parent.parent / "static" / "vk_miniapp" / "index.html"
    if not path.is_file():
        return HTMLResponse("<p>Template static/vk_miniapp/index.html not found.</p>", status_code=404)
    peer = f"-{gid}" if gid else ""
    html = path.read_text(encoding="utf-8").replace("{{IM_PEER}}", peer)
    # Разрешаем встраивание во iframe клиента VK (без *. — часть браузеров строже парсит wildcard).
    csp = (
        "frame-ancestors https://vk.com https://m.vk.com https://vk.ru https://m.vk.ru "
        "https://web.vk.com https://oauth.vk.com https://id.vk.com;"
    )
    return HTMLResponse(html, headers={"Content-Security-Policy": csp})


@app.get("/")
@app.get("/healthz")
async def healthz() -> dict[str, str]:
    # На части машин локальный прокси отдаёт 405 на /healthz; для балансировщиков используйте GET /
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict[str, object]:
    session_ok = await runtime.session_store.ready()
    outbox_ok = await runtime.outbox.ready()
    media_ok = await runtime.media_cache.ready()
    queue_size = await runtime.outbox.queue_size()
    return {
        "status": "ok" if session_ok and outbox_ok and media_ok else "degraded",
        "redis_configured": bool(settings.redis_url),
        "session_store": session_ok,
        "outbox": outbox_ok,
        "media_cache": media_ok,
        "queue_size": queue_size,
    }


@app.get("/metrics")
async def metrics():
    return metrics_response()


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> Response:
    started = time.monotonic()
    if not settings.has_telegram:
        raise HTTPException(status_code=503, detail="Telegram is not configured")

    if settings.telegram_webhook_secret:
        got = (request.headers.get("X-Telegram-Bot-Api-Secret-Token") or "").strip()
        if got != settings.telegram_webhook_secret:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Webhook secret: заголовок X-Telegram-Bot-Api-Secret-Token не совпадает с TELEGRAM_WEBHOOK_SECRET. "
                    "Либо вызовите setWebhook с тем же secret_token, либо удалите/очистите TELEGRAM_WEBHOOK_SECRET в .env."
                ),
            )

    bot: Bot = request.app.state.tg_bot
    dp = request.app.state.tg_dp

    data = await request.body()
    update = Update.model_validate_json(data)
    await dp.feed_update(bot, update)
    WEBHOOK_EVENTS.labels("tg", "update", "ok").inc()
    WEBHOOK_LATENCY.labels("tg", "update").observe(time.monotonic() - started)
    return Response(content="ok", media_type="text/plain")
