from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

from app.game_engine import apply_answer, start_game
from app import runtime
from app.config import Settings
from app import vk_client
from app.vk_delivery import send_vk_segments


def _is_start(text: str | None) -> bool:
    if not text:
        return False
    t = text.strip().lower()
    return t in ("/start", "start", "старт", "начать", "/старт")


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
            msg = body.get("object", {}).get("message") or {}
            text = msg.get("text")
            peer_id = msg.get("peer_id")
            from_id = msg.get("from_id")
            if peer_id is None or from_id is None:
                return Response(content="ok", media_type="text/plain")

            if _is_start(text):
                session, segments = start_game()
                runtime.vk_sessions[int(from_id)] = session
                token = settings.vk_api_token or ""
                gid = int(settings.vk_group_id or 0)
                await send_vk_segments(token=token, group_id=gid, peer_id=int(peer_id), segments=segments)
            return Response(content="ok", media_type="text/plain")

        if body.get("type") == "message_event":
            obj = body.get("object") or {}
            event_id = str(obj.get("event_id") or "")
            user_id = int(obj.get("user_id") or 0)
            peer_id = int(obj.get("peer_id") or 0)
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
            gid = int(settings.vk_group_id or 0)

            if event_id and user_id and peer_id:
                try:
                    await vk_client.vk_send_message_event_answer(
                        token, event_id=event_id, user_id=user_id, peer_id=peer_id
                    )
                except vk_client.VkApiError:
                    pass

            session = runtime.vk_sessions.get(user_id)
            if session is None or session.finished or not option_id:
                return Response(content="ok", media_type="text/plain")

            session, segments = apply_answer(session, option_id)
            runtime.vk_sessions[user_id] = session
            await send_vk_segments(token=token, group_id=gid, peer_id=peer_id, segments=segments)
            return Response(content="ok", media_type="text/plain")

        return Response(content="ok", media_type="text/plain")

    return router
