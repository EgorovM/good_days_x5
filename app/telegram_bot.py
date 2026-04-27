from __future__ import annotations

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.game_engine import acknowledge_intro, apply_answer, continue_stage, start_game
from app import runtime
from app.outbox import OutboxTask


def build_tg_router() -> Router:
    router = Router()

    @router.message(CommandStart())
    async def cmd_start(message: Message, bot: Bot) -> None:
        if not message.from_user:
            return
        uid = message.from_user.id
        session, segments = start_game()
        await runtime.session_store.set("tg", uid, session)
        await runtime.outbox.enqueue(
            OutboxTask(
                platform="tg",
                recipient_id=message.chat.id,
                segments=segments,
                dedupe_key=f"tg:start:{uid}:{message.message_id}",
            )
        )

    @router.callback_query(F.data.startswith("nav:"))
    async def on_nav(query: CallbackQuery, bot: Bot) -> None:
        if not query.from_user or not query.message:
            return
        code = (query.data or "")[4:]
        uid = query.from_user.id
        session = await runtime.session_store.get("tg", uid)
        if session is None:
            await query.answer("Сначала нажми /start", show_alert=True)
            return
        if code == "go":
            session, segments = acknowledge_intro(session)
        elif code == "next":
            session, segments = continue_stage(session)
        else:
            await query.answer()
            return
        await runtime.session_store.set("tg", uid, session)
        await query.answer()
        await runtime.outbox.enqueue(
            OutboxTask(
                platform="tg",
                recipient_id=query.message.chat.id,
                segments=segments,
                dedupe_key=f"tg:nav:{query.id}",
            )
        )

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
        session = await runtime.session_store.get("tg", uid)
        if session is None or session.finished:
            await query.answer("Сначала нажми /start", show_alert=True)
            return
        session, segments = apply_answer(session, option_id)
        await runtime.session_store.set("tg", uid, session)
        await query.answer()
        await runtime.outbox.enqueue(
            OutboxTask(
                platform="tg",
                recipient_id=query.message.chat.id,
                segments=segments,
                dedupe_key=f"tg:ans:{query.id}",
            )
        )

    return router


def build_tg_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(build_tg_router())
    return dp
