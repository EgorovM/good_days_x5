from __future__ import annotations

import json

from app import runtime
from app.formatting import vk_plain
from app.game_engine import Segment
from app.vk_richtext import build_vk_message
from app.media import image_public_url
from app.paths import STATIC_IMAGES_DIR
from app import vk_client


def _vk_callback_payload(oid: str) -> dict[str, str]:
    if oid.startswith("nav:"):
        return {"n": oid[4:]}
    if oid.startswith("ans:"):
        return {"o": oid[4:]}
    return {"o": oid}


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
                    "payload": json.dumps(_vk_callback_payload(oid), ensure_ascii=False, separators=(",", ":")),
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
        vk_body, fmt_data = build_vk_message(raw, seg.kind) if raw else ("", None)
        if seg.image and url and not attachment:
            text = (vk_body + "\n\n" + vk_plain(url)).strip() if vk_body else vk_plain(url)
        else:
            text = vk_body
        kb = _vk_keyboard_json(seg.options)
        try:
            await vk_client.vk_send_message(
                token,
                peer_id=peer_id,
                text=text or None,
                attachment=attachment,
                keyboard=kb,
                format_data=fmt_data,
            )
        except vk_client.VkApiError as e:
            if e.error_code == 912 and kb:
                tail = (
                    "\n\nОтветь одной латинской буквой в следующем сообщении: A, B или C.\n"
                    "(Кнопки появятся, если в сообществе включить: Сообщения → Настройки для бота → «Возможности ботов».)"
                )
                retry_text = ((text or "") + vk_plain(tail)).strip()
                await vk_client.vk_send_message(
                    token,
                    peer_id=peer_id,
                    text=retry_text or None,
                    attachment=attachment,
                    keyboard=None,
                    format_data=fmt_data,
                )
            else:
                raise
