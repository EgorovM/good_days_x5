from __future__ import annotations

from typing import Any


def extract_message_new(body: dict[str, Any]) -> dict[str, Any] | None:
    """
    VK Callback message_new: в разных версиях API object либо { "message": {...} }, либо само сообщение.
    """
    if body.get("type") != "message_new":
        return None
    obj = body.get("object")
    if not isinstance(obj, dict):
        return None
    inner = obj.get("message")
    if isinstance(inner, dict):
        return inner
    if "peer_id" in obj or "from_id" in obj or "conversation_message_id" in obj:
        return obj
    return None


def extract_message_event(body: dict[str, Any]) -> dict[str, Any] | None:
    if body.get("type") != "message_event":
        return None
    obj = body.get("object")
    return obj if isinstance(obj, dict) else None
