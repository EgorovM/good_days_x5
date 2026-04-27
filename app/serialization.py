from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.game_engine import Segment


def segment_to_dict(seg: Segment) -> dict[str, Any]:
    data = asdict(seg)
    if seg.options is not None:
        data["options"] = [[oid, label] for oid, label in seg.options]
    return data


def segment_from_dict(data: dict[str, Any]) -> Segment:
    options = data.get("options")
    return Segment(
        text=data.get("text"),
        image=data.get("image"),
        options=[(str(oid), str(label)) for oid, label in options] if options else None,
        kind=str(data.get("kind") or "plain"),
    )


def segments_to_dicts(segments: list[Segment]) -> list[dict[str, Any]]:
    return [segment_to_dict(seg) for seg in segments]


def segments_from_dicts(items: list[dict[str, Any]]) -> list[Segment]:
    return [segment_from_dict(item) for item in items]
