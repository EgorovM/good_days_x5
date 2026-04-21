from __future__ import annotations

import json

from app import runtime
from app.game_engine import Segment
from app.media import image_public_url
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
        if seg.image and url:
            attachment = await vk_client.vk_upload_photo_from_url(
                token, group_id=group_id, peer_id=peer_id, image_url=url
            )
        text = seg.text or ""
        if seg.image and url and not attachment:
            text = (text + f"\n\n{url}").strip()
        kb = _vk_keyboard_json(seg.options)
        await vk_client.vk_send_message(
            token,
            peer_id=peer_id,
            text=text or None,
            attachment=attachment,
            keyboard=kb,
        )
