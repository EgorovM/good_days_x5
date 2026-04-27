from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app import runtime
from app.telegram_bot import build_tg_dispatcher
from app.vk_router import build_vk_router

settings = get_settings()
runtime.settings = settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.has_telegram:
        app.state.tg_bot = Bot(
            settings.telegram_bot_token,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        app.state.tg_dp = build_tg_dispatcher()
    yield
    if getattr(app.state, "tg_bot", None):
        await app.state.tg_bot.session.close()


app = FastAPI(title="X5 Good Days bot", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(build_vk_router(settings))


@app.get("/vk/miniapp", response_class=HTMLResponse)
async def vk_miniapp_page() -> HTMLResponse:
    """Статическая страница для VK Mini App: кнопка открывает чат с сообществом (настройте URL приложения в кабинете VK)."""
    gid = abs(int(settings.vk_group_id or 0))
    path = Path(__file__).resolve().parent.parent / "static" / "vk_miniapp" / "index.html"
    if not path.is_file():
        return HTMLResponse("<p>Template static/vk_miniapp/index.html not found.</p>", status_code=404)
    peer = f"-{gid}" if gid else ""
    html = path.read_text(encoding="utf-8").replace("{{IM_PEER}}", peer)
    return HTMLResponse(html)


@app.get("/")
@app.get("/healthz")
async def healthz() -> dict[str, str]:
    # На части машин локальный прокси отдаёт 405 на /healthz; для балансировщиков используйте GET /
    return {"status": "ok"}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> Response:
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
    return Response(content="ok", media_type="text/plain")
