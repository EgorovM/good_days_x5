from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from app.formatting import format_segment_vk
from app.game_engine import apply_answer, start_game
from app import runtime
from app.config import Settings
from app import vk_client
from app.vk_delivery import send_vk_segments
from app.vk_payload import extract_message_event, extract_message_new

log = logging.getLogger(__name__)


def _is_start(text: str | None) -> bool:
    if not text:
        return False
    t = text.strip().lower()
    return t in ("/start", "start", "старт", "начать", "/старт")


def _option_letter(text: object) -> str | None:
    """Один символ A/B/C — ответ без callback-кнопок (например при ошибке 912)."""
    if not isinstance(text, str):
        return None
    t = text.strip().upper()
    if len(t) == 1 and t in "ABC":
        return t
    return None


def build_vk_router(settings: Settings) -> APIRouter:
    router = APIRouter()

    @router.post("/vk/callback")
    async def vk_callback(request: Request) -> Response:
        if not settings.has_vk:
            raise HTTPException(status_code=503, detail="VK is not configured")

        body = await request.json()

        if settings.vk_secret and body.get("secret") != settings.vk_secret:
            raise HTTPException(status_code=403, detail="Bad secret")

        if body.get("type") == "confirmation":
            return Response(content=settings.vk_callback_confirmation or "", media_type="text/plain")

        if body.get("type") == "message_new":
            msg = extract_message_new(body) or {}
            if not msg:
                return Response(content="ok", media_type="text/plain")

            # Исходящие сообщения сообщества не обрабатываем (избегаем петель)
            if msg.get("out") == 1:
                return Response(content="ok", media_type="text/plain")

            text = msg.get("text")
            peer_id = msg.get("peer_id")
            from_id = msg.get("from_id")
            if peer_id is None or from_id is None:
                log.warning("VK message_new без peer_id/from_id: keys=%s", list(msg.keys())[:20])
                return Response(content="ok", media_type="text/plain")

            peer_id = int(peer_id)
            from_id = int(from_id)
            token = settings.vk_api_token or ""
            gid = abs(int(settings.vk_group_id or 0))

            async def _hint(message: str) -> None:
                try:
                    await vk_client.vk_send_message(
                        token,
                        peer_id=peer_id,
                        text=format_segment_vk(message, "plain"),
                        content_format=1,
                    )
                except vk_client.VkApiError:
                    log.exception("VK messages.send (hint) failed peer_id=%s", peer_id)

            try:
                if _is_start(text):
                    session, segments = start_game()
                    runtime.vk_sessions[from_id] = session
                    await send_vk_segments(token=token, group_id=gid, peer_id=peer_id, segments=segments)
                else:
                    letter = _option_letter(text)
                    session = runtime.vk_sessions.get(from_id)
                    if letter and session and not session.finished:
                        session, segments = apply_answer(session, letter)
                        runtime.vk_sessions[from_id] = session
                        await send_vk_segments(token=token, group_id=gid, peer_id=peer_id, segments=segments)
                    elif session is None or session.finished:
                        await _hint("Чтобы начать квест, напиши: старт или /start")
                    else:
                        await _hint(
                            "Выбери ответ кнопкой A, B или C под сообщением, "
                            "или напиши одну букву A, B или C. Чтобы начать заново — напиши «старт»."
                        )
            except vk_client.VkApiError:
                log.exception("VK message_new handling failed from_id=%s peer_id=%s", from_id, peer_id)

            return Response(content="ok", media_type="text/plain")

        if body.get("type") == "message_event":
            obj = extract_message_event(body) or {}
            event_id = str(obj.get("event_id") or "")
            user_id = int(obj.get("user_id") or 0)
            peer_id = int(obj.get("peer_id") or 0)
            if peer_id <= 0 and user_id > 0:
                peer_id = user_id

            raw_payload = obj.get("payload")
            payload: dict[str, Any] = {}
            if isinstance(raw_payload, str):
                try:
                    payload = json.loads(raw_payload)
                except json.JSONDecodeError:
                    payload = {}
            elif isinstance(raw_payload, dict):
                payload = raw_payload

            option_id = str(payload.get("o") or "")
            token = settings.vk_api_token or ""
            gid = abs(int(settings.vk_group_id or 0))

            if event_id and user_id and peer_id:
                try:
                    await vk_client.vk_send_message_event_answer(
                        token, event_id=event_id, user_id=user_id, peer_id=peer_id
                    )
                except vk_client.VkApiError:
                    log.exception("VK sendMessageEventAnswer failed")

            session = runtime.vk_sessions.get(user_id)
            if session is None or session.finished or not option_id:
                return Response(content="ok", media_type="text/plain")

            try:
                session, segments = apply_answer(session, option_id)
                runtime.vk_sessions[user_id] = session
                await send_vk_segments(token=token, group_id=gid, peer_id=peer_id, segments=segments)
            except vk_client.VkApiError:
                log.exception("VK message_event send failed user_id=%s", user_id)

            return Response(content="ok", media_type="text/plain")

        return Response(content="ok", media_type="text/plain")

    return router
