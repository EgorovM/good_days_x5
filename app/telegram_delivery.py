from __future__ import annotations

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.types import FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, URLInputFile

from app.formatting import esc, format_segment_html
from app.game_engine import Segment
from app import runtime
from app.media import image_public_url
from app.paths import STATIC_IMAGES_DIR


def _inline_keyboard(options: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(text=label, callback_data=f"ans:{oid}") for oid, label in options]
    return InlineKeyboardMarkup(inline_keyboard=[row])


async def send_telegram_segments(bot: Bot, chat_id: int, segments: list[Segment]) -> None:
    base = runtime.settings.public_base_url if runtime.settings else None
    for seg in segments:
        raw = seg.text or ""
        caption = (format_segment_html(raw, seg.kind)[:1024] if raw else None) or None
        local = (STATIC_IMAGES_DIR / seg.image) if seg.image else None

        if seg.image and local and local.is_file():
            await bot.send_photo(
                chat_id, FSInputFile(local), caption=caption, parse_mode=ParseMode.HTML if caption else None
            )
            continue

        url = image_public_url(base, seg.image)
        if seg.image and url:
            try:
                await bot.send_photo(
                    chat_id, URLInputFile(url), caption=caption, parse_mode=ParseMode.HTML if caption else None
                )
            except (TelegramBadRequest, TelegramNetworkError):
                note = esc(
                    (raw + "\n\n(Картинка по URL недоступна; добавьте файл в static/images)").strip()
                )
                await bot.send_message(chat_id, note, parse_mode=ParseMode.HTML)
            continue

        if seg.image and not url:
            note = esc(
                (raw + "\n\n(Картинка: задайте PUBLIC_BASE_URL или положите файл в static/images)").strip()
            )
            await bot.send_message(chat_id, note, parse_mode=ParseMode.HTML)
            continue

        if seg.text:
            kb = _inline_keyboard(seg.options) if seg.options else None
            body = format_segment_html(seg.text, seg.kind)
            await bot.send_message(chat_id, body, reply_markup=kb, parse_mode=ParseMode.HTML)
