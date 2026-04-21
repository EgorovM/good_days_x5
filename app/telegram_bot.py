from __future__ import annotations

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.game_engine import apply_answer, start_game
from app import runtime
from app.telegram_delivery import send_telegram_segments


def build_tg_router() -> Router:
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(message: Message, bot: Bot) -> None:
        if not message.from_user:
            return
        uid = message.from_user.id
        session, segments = start_game()
        runtime.tg_sessions[uid] = session
        await send_telegram_segments(bot, message.chat.id, segments)

    @router.callback_query(F.data.startswith("ans:"))
    async def on_answer(query: CallbackQuery, bot: Bot) -> None:
        if not query.from_user or not query.message:
            return
        parts = (query.data or "").split(":")
        if len(parts) != 2:
            await query.answer()
            return
        option_id = parts[1]
        uid = query.from_user.id
        session = runtime.tg_sessions.get(uid)
        if session is None or session.finished:
            await query.answer("Сначала нажми /start", show_alert=True)
            return
        session, segments = apply_answer(session, option_id)
        runtime.tg_sessions[uid] = session
        await query.answer()
        await send_telegram_segments(bot, query.message.chat.id, segments)

    return router


def build_tg_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(build_tg_router())
    return dp
