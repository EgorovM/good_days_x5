from __future__ import annotations

import asyncio
import json
import random
from typing import Any

import httpx

VK_API_VERSION = "5.199"

# Один клиент на процесс: переиспользование TCP/TLS к api.vk.com и к upload-серверам.
_api_timeout = httpx.Timeout(22.0, connect=3.5)
_upload_timeout = httpx.Timeout(90.0, connect=10.0)
_download_timeout = httpx.Timeout(35.0, connect=5.0)

_http_client: httpx.AsyncClient | None = None
_http_lock = asyncio.Lock()


async def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is not None and not _http_client.is_closed:
        return _http_client
    async with _http_lock:
        if _http_client is not None and not _http_client.is_closed:
            return _http_client
        _http_client = httpx.AsyncClient(
            limits=httpx.Limits(max_connections=256, max_keepalive_connections=64),
            timeout=_api_timeout,
            headers={"User-Agent": "good-days-x5/vk"},
        )
        return _http_client


async def aclose_http_client() -> None:
    """Закрыть пул соединений (вызов из lifespan FastAPI)."""
    global _http_client
    async with _http_lock:
        c = _http_client
        _http_client = None
        if c is not None and not c.is_closed:
            await c.aclose()


class VkApiError(RuntimeError):
    """Ошибка VK API; error_code — для обработки (например 912 «возможности ботов»)."""

    def __init__(self, message: str, *, error_code: int | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


async def vk_call(token: str, method: str, **params: Any) -> Any:
    data = {"access_token": token, "v": VK_API_VERSION, **params}
    client = await get_http_client()
    resp = await client.post(
        f"https://api.vk.com/method/{method}",
        data=data,
        timeout=_api_timeout,
    )
    resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        err = payload["error"]
        code = err.get("error_code")
        msg = err.get("error_msg", "")
        text = f"{code} {msg}"
        if code == 912:
            text += (
                " | ВКонтакте: Управление сообществом → Сообщения → Настройки для бота → "
                "«Возможности ботов» — Включены (обязательно для кнопок и клавиатур)."
            )
        raise VkApiError(text, error_code=code if isinstance(code, int) else None)
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


async def _save_messages_photo_after_upload(token: str, data: dict[str, Any]) -> Any:
    photo_field = data.get("photo")
    if isinstance(photo_field, str):
        return await vk_call(
            token,
            "photos.saveMessagesPhoto",
            photo=photo_field,
            server=data["server"],
            hash=data["hash"],
        )
    return await vk_call(
        token,
        "photos.saveMessagesPhoto",
        photo=data["photo"],
        server=data["server"],
        hash=data["hash"],
    )


async def vk_upload_photo_bytes(
    token: str,
    *,
    group_id: int,
    peer_id: int,
    data: bytes,
    filename: str = "image.png",
) -> str | None:
    """Загрузка PNG/JPEG в сообщения VK; возвращает attachment photo... или None."""
    try:
        upload = await vk_call(token, "photos.getMessagesUploadServer", group_id=group_id, peer_id=peer_id)
        upload_url = upload["upload_url"]
        ctype = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
        client = await get_http_client()
        files = {"photo": (filename, data, ctype)}
        up = await client.post(upload_url, files=files, timeout=_upload_timeout)
        up.raise_for_status()
        payload = up.json()
        saved = await _save_messages_photo_after_upload(token, payload)
        if not saved:
            return None
        ph = saved[0]
        return f"photo{ph['owner_id']}_{ph['id']}"
    except (VkApiError, httpx.HTTPError, KeyError, json.JSONDecodeError, TypeError, IndexError):
        return None


async def vk_upload_photo_from_url(
    token: str,
    *,
    group_id: int,
    peer_id: int,
    image_url: str,
) -> str | None:
    """Скачивает по URL и загружает в VK."""
    try:
        client = await get_http_client()
        img = await client.get(image_url, timeout=_download_timeout)
        img.raise_for_status()
        body = img.content
        name = image_url.rsplit("/", 1)[-1][:64] or "photo.jpg"
        return await vk_upload_photo_bytes(
            token, group_id=group_id, peer_id=peer_id, data=body, filename=name
        )
    except (httpx.HTTPError, VkApiError):
        return None


async def vk_send_message(
    token: str,
    *,
    peer_id: int,
    text: str | None = None,
    attachment: str | None = None,
    keyboard: str | None = None,
    format_data: str | None = None,
) -> None:
    """format_data — JSON-строка {version:1, items:[{type,offset,length},...]} (UTF-16), см. messages.send."""
    params: dict[str, Any] = {"peer_id": peer_id, "random_id": random.randint(1, 2_147_000_000)}
    if text:
        params["message"] = text
    if attachment:
        params["attachment"] = attachment
    if keyboard:
        params["keyboard"] = keyboard
    if format_data:
        params["format_data"] = format_data
    if "message" not in params and not attachment:
        params["message"] = "\u200b"
    await vk_call(token, "messages.send", **params)
