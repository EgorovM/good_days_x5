from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, URLInputFile

from app.formatting import esc, format_segment_html
from app.game_engine import Segment
from app import runtime
from app.media import image_public_url
from app.paths import STATIC_IMAGES_DIR

TG_CAPTION_MAX = 1024


def _callback_data(oid: str) -> str:
    if oid.startswith(("nav:", "ans:")):
        return oid[:64]
    return f"ans:{oid}"[:64]


def _inline_keyboard(options: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(text=label, callback_data=_callback_data(oid)) for oid, label in options]
    return InlineKeyboardMarkup(inline_keyboard=[row])


def _truncate_caption(html: str) -> str:
    if len(html) <= TG_CAPTION_MAX:
        return html
    return html[: TG_CAPTION_MAX - 1] + "…"


async def send_telegram_segments(bot: Bot, chat_id: int, segments: list[Segment]) -> None:
    base = runtime.settings.public_base_url if runtime.settings else None
    for seg in segments:
        raw = seg.text or ""
        caption_html = (format_segment_html(raw, seg.kind) if raw else None) or None
        if caption_html:
            caption_html = _truncate_caption(caption_html)
        kb = _inline_keyboard(seg.options) if seg.options else None
        local = (STATIC_IMAGES_DIR / seg.image) if seg.image else None

        if seg.image and local and local.is_file():
            photo_bytes = await asyncio.to_thread(local.read_bytes)
            await bot.send_photo(
                chat_id,
                BufferedInputFile(photo_bytes, filename=seg.image),
                caption=caption_html,
                parse_mode=ParseMode.HTML if caption_html else None,
                reply_markup=kb,
            )
            continue

        url = image_public_url(base, seg.image)
        if seg.image and url:
            try:
                await bot.send_photo(
                    chat_id,
                    URLInputFile(url),
                    caption=caption_html,
                    parse_mode=ParseMode.HTML if caption_html else None,
                    reply_markup=kb,
                )
            except (TelegramBadRequest, TelegramNetworkError):
                note = esc(
                    (raw + "\n\n(Картинка по URL недоступна; добавьте файл в static/images)").strip()
                )
                await bot.send_message(chat_id, note, parse_mode=ParseMode.HTML, reply_markup=kb)
            continue

        if seg.image and not url:
            note = esc(
                (raw + "\n\n(Картинка: задайте PUBLIC_BASE_URL или положите файл в static/images)").strip()
            )
            await bot.send_message(chat_id, note, parse_mode=ParseMode.HTML, reply_markup=kb)
            continue

        if seg.text:
            body = format_segment_html(seg.text, seg.kind)
            await bot.send_message(chat_id, body, reply_markup=kb, parse_mode=ParseMode.HTML)
