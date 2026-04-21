from __future__ import annotations

import json

from app import runtime
from app.formatting import format_segment_vk, vk_plain
from app.game_engine import Segment
from app.media import image_public_url
from app.paths import STATIC_IMAGES_DIR
from app import vk_client


def _vk_keyboard_json(options: list[tuple[str, str]] | None) -> str | None:
    if not options:
        return None
    row = []
    for oid, label in options:
        row.append(
            {
                "action": {
                    "type": "callback",
                    "label": label[:40],
                    "payload": json.dumps({"o": oid}),
                },
                "color": "secondary",
            }
        )
    return json.dumps({"inline": True, "buttons": [row]}, ensure_ascii=False)


async def send_vk_segments(*, token: str, group_id: int, peer_id: int, segments: list[Segment]) -> None:
    base = runtime.settings.public_base_url if runtime.settings else None
    for seg in segments:
        url = image_public_url(base, seg.image)
        attachment: str | None = None
        local = (STATIC_IMAGES_DIR / seg.image) if seg.image else None
        if seg.image and local and local.is_file():
            attachment = await vk_client.vk_upload_photo_bytes(
                token,
                group_id=group_id,
                peer_id=peer_id,
                data=local.read_bytes(),
                filename=seg.image,
            )
        elif seg.image and url:
            attachment = await vk_client.vk_upload_photo_from_url(
                token, group_id=group_id, peer_id=peer_id, image_url=url
            )
        raw = seg.text or ""
        vk_body = format_segment_vk(raw, seg.kind) if raw else ""
        if seg.image and url and not attachment:
            text = (vk_body + "\n\n" + vk_plain(url)).strip() if vk_body else vk_plain(url)
        else:
            text = vk_body
        kb = _vk_keyboard_json(seg.options)
        fmt = 1 if text else None  # VK: format=1 — markdown (HTML format=2 в чатах часто не рендерится)
        try:
            await vk_client.vk_send_message(
                token,
                peer_id=peer_id,
                text=text or None,
                attachment=attachment,
                keyboard=kb,
                content_format=fmt,
            )
        except vk_client.VkApiError as e:
            if e.error_code == 912 and kb:
                tail = (
                    "\n\nОтветь одной латинской буквой в следующем сообщении: A, B или C.\n"
                    "(Кнопки появятся, если в сообществе включить: Сообщения → Настройки для бота → «Возможности ботов».)"
                )
                await vk_client.vk_send_message(
                    token,
                    peer_id=peer_id,
                    text=((text or "") + vk_plain(tail)).strip(),
                    attachment=attachment,
                    keyboard=None,
                    content_format=fmt,
                )
            else:
                raise
