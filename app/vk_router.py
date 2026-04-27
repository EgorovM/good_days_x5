from __future__ import annotations

import json
import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from app.game_engine import Segment, acknowledge_intro, apply_answer, continue_stage, start_game
from app import runtime
from app.config import Settings
from app.metrics import WEBHOOK_EVENTS, WEBHOOK_LATENCY
from app.outbox import OutboxTask
from app import vk_client
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
        started = time.monotonic()
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

            async def _enqueue_segments(segments: list[Segment], dedupe_key: str) -> None:
                await runtime.outbox.enqueue(
                    OutboxTask(platform="vk", recipient_id=peer_id, segments=segments, dedupe_key=dedupe_key)
                )

            async def _hint(message: str, dedupe_key: str) -> None:
                await _enqueue_segments([Segment(text=message, kind="plain")], dedupe_key)

            try:
                if _is_start(text):
                    session, segments = start_game()
                    await runtime.session_store.set("vk", from_id, session)
                    await _enqueue_segments(
                        segments,
                        f"vk:start:{from_id}:{peer_id}:{msg.get('conversation_message_id') or msg.get('id') or time.time_ns()}",
                    )
                else:
                    letter = _option_letter(text)
                    session = await runtime.session_store.get("vk", from_id)
                    if letter and session and not session.finished:
                        if session.intro_pending:
                            await _hint(
                                "Сначала нажми кнопку «Поехали!» под приветствием.",
                                f"vk:hint:intro:{from_id}:{peer_id}:{msg.get('conversation_message_id')}",
                            )
                        elif session.continue_pending:
                            await _hint(
                                "Сначала нажми «Следующий этап» или «Финальный этап», чтобы продолжить.",
                                f"vk:hint:continue:{from_id}:{peer_id}:{msg.get('conversation_message_id')}",
                            )
                        else:
                            session, segments = apply_answer(session, letter)
                            await runtime.session_store.set("vk", from_id, session)
                            await _enqueue_segments(
                                segments,
                                f"vk:text-answer:{from_id}:{peer_id}:{msg.get('conversation_message_id') or msg.get('id') or time.time_ns()}",
                            )
                    elif session is None or session.finished:
                        await _hint(
                            "Чтобы начать квест, напиши: старт или /start",
                            f"vk:hint:start:{from_id}:{peer_id}:{msg.get('conversation_message_id')}",
                        )
                    else:
                        await _hint(
                            "Выбери ответ кнопкой A, B или C под сообщением, "
                            "или напиши одну букву A, B или C. Чтобы начать заново — напиши «старт».",
                            f"vk:hint:choice:{from_id}:{peer_id}:{msg.get('conversation_message_id')}",
                        )
            except Exception:
                WEBHOOK_EVENTS.labels("vk", "message_new", "error").inc()
                log.exception("VK message_new handling failed from_id=%s peer_id=%s", from_id, peer_id)

            WEBHOOK_EVENTS.labels("vk", "message_new", "ok").inc()
            WEBHOOK_LATENCY.labels("vk", "message_new").observe(time.monotonic() - started)
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

            nav = str(payload.get("n") or "")
            option_id = str(payload.get("o") or "")
            token = settings.vk_api_token or ""

            if event_id and user_id and peer_id:
                try:
                    await vk_client.vk_send_message_event_answer(
                        token, event_id=event_id, user_id=user_id, peer_id=peer_id
                    )
                except vk_client.VkApiError:
                    log.exception("VK sendMessageEventAnswer failed")

            session = await runtime.session_store.get("vk", user_id)

            try:
                if nav == "go":
                    if session is None:
                        return Response(content="ok", media_type="text/plain")
                    session, segments = acknowledge_intro(session)
                    await runtime.session_store.set("vk", user_id, session)
                    await runtime.outbox.enqueue(
                        OutboxTask(
                            platform="vk",
                            recipient_id=peer_id,
                            segments=segments,
                            dedupe_key=f"vk:event:go:{event_id or time.time_ns()}",
                        )
                    )
                    return Response(content="ok", media_type="text/plain")

                if nav == "next":
                    if session is None:
                        return Response(content="ok", media_type="text/plain")
                    session, segments = continue_stage(session)
                    await runtime.session_store.set("vk", user_id, session)
                    await runtime.outbox.enqueue(
                        OutboxTask(
                            platform="vk",
                            recipient_id=peer_id,
                            segments=segments,
                            dedupe_key=f"vk:event:next:{event_id or time.time_ns()}",
                        )
                    )
                    return Response(content="ok", media_type="text/plain")

                if not option_id or session is None or session.finished:
                    return Response(content="ok", media_type="text/plain")

                session, segments = apply_answer(session, option_id)
                await runtime.session_store.set("vk", user_id, session)
                await runtime.outbox.enqueue(
                    OutboxTask(
                        platform="vk",
                        recipient_id=peer_id,
                        segments=segments,
                        dedupe_key=f"vk:event:ans:{event_id or time.time_ns()}",
                    )
                )
            except Exception:
                WEBHOOK_EVENTS.labels("vk", "message_event", "error").inc()
                log.exception("VK message_event send failed user_id=%s", user_id)

            WEBHOOK_EVENTS.labels("vk", "message_event", "ok").inc()
            WEBHOOK_LATENCY.labels("vk", "message_event").observe(time.monotonic() - started)
            return Response(content="ok", media_type="text/plain")

        return Response(content="ok", media_type="text/plain")

    return router
