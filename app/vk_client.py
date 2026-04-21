from __future__ import annotations

import json
import random
from typing import Any

import httpx

VK_API_VERSION = "5.199"


class VkApiError(RuntimeError):
    pass


async def vk_call(token: str, method: str, **params: Any) -> Any:
    data = {"access_token": token, "v": VK_API_VERSION, **params}
    async with httpx.AsyncClient(timeout=45) as client:
        resp = await client.post(f"https://api.vk.com/method/{method}", data=data)
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        err = payload["error"]
        raise VkApiError(f"{err.get('error_code')} {err.get('error_msg')}")
    return payload["response"]


async def vk_send_message_event_answer(
    token: str,
    *,
    event_id: str,
    user_id: int,
    peer_id: int,
) -> None:
    await vk_call(
        token,
        "messages.sendMessageEventAnswer",
        event_id=event_id,
        user_id=user_id,
        peer_id=peer_id,
    )


async def vk_upload_photo_from_url(
    token: str,
    *,
    group_id: int,
    peer_id: int,
    image_url: str,
) -> str | None:
    """Возвращает attachment-строку photo... или None, если загрузка не удалась."""
    try:
        upload = await vk_call(token, "photos.getMessagesUploadServer", group_id=group_id, peer_id=peer_id)
        upload_url = upload["upload_url"]
        async with httpx.AsyncClient(timeout=60) as client:
            img = await client.get(image_url)
            img.raise_for_status()
            files = {"photo": ("photo.jpg", img.content, img.headers.get("content-type", "image/jpeg"))}
            up = await client.post(upload_url, files=files)
        up.raise_for_status()
        data = up.json()
        photo_field = data.get("photo")
        if isinstance(photo_field, str):
            saved = await vk_call(token, "photos.saveMessagesPhoto", photo=photo_field, server=data["server"], hash=data["hash"])
        else:
            saved = await vk_call(
                token,
                "photos.saveMessagesPhoto",
                photo=data["photo"],
                server=data["server"],
                hash=data["hash"],
            )
        if not saved:
            return None
        ph = saved[0]
        return f"photo{ph['owner_id']}_{ph['id']}"
    except (VkApiError, httpx.HTTPError, KeyError, json.JSONDecodeError):
        return None


async def vk_send_message(
    token: str,
    *,
    peer_id: int,
    text: str | None = None,
    attachment: str | None = None,
    keyboard: str | None = None,
) -> None:
    params: dict[str, Any] = {"peer_id": peer_id, "random_id": random.randint(1, 2_147_000_000)}
    if text:
        params["message"] = text
    if attachment:
        params["attachment"] = attachment
    if keyboard:
        params["keyboard"] = keyboard
    if "message" not in params and not attachment:
        # VK требует хотя бы одно из: message / attachment / ...
        params["message"] = "\u200b"
    await vk_call(token, "messages.send", **params)
