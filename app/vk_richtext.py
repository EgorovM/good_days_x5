from __future__ import annotations

import json
import re
from typing import Any


def _utf16_len(s: str) -> int:
    n = 0
    for ch in s:
        n += 2 if ord(ch) > 0xFFFF else 1
    return n


def _utf16_span(full: str, start_char: int, end_char_exclusive: int) -> tuple[int, int]:
    """offset и length в UTF-16 code units (как в Telegram entities / VK format_data)."""
    off = _utf16_len(full[:start_char])
    ln = _utf16_len(full[start_char:end_char_exclusive])
    return off, ln


def _dump(items: list[dict[str, Any]]) -> str:
    return json.dumps({"version": 1, "items": items}, ensure_ascii=False, separators=(",", ":"))


def build_vk_message(text: str | None, kind: str) -> tuple[str, str | None]:
    """
    Плоский текст + format_data для VK messages.send (API 5.199+).
    Без литералов *…* и без format=1 — только параметр format_data.
    """
    if not text:
        return "", None
    if kind == "plain":
        return text, None
    if kind == "intro":
        return _intro(text)
    if kind == "question":
        return _question(text)
    if kind == "feedback":
        return _feedback(text)
    if kind == "finale":
        return _finale(text)
    return text, None


def _intro(text: str) -> tuple[str, str | None]:
    lines = text.split("\n")
    if not lines or not lines[0].strip():
        return text, None
    first = lines[0]
    off, ln = _utf16_span(text, 0, len(first))
    return text, _dump([{"type": "bold", "offset": off, "length": ln}])


def _question(text: str) -> tuple[str, str | None]:
    lines = text.split("\n")
    starts: list[int] = []
    pos = 0
    for i, line in enumerate(lines):
        starts.append(pos)
        pos += len(line)
        if i < len(lines) - 1:
            pos += 1
    items: list[dict[str, Any]] = []
    if lines and lines[0].strip():
        s0, e0 = starts[0], starts[0] + len(lines[0])
        o, l = _utf16_span(text, s0, e0)
        items.append({"type": "bold", "offset": o, "length": l})
    for i, line in enumerate(lines):
        if i == 0:
            continue
        stripped = line.lstrip()
        if not re.match(r"^[A-C]:", stripped):
            continue
        prefix = len(line) - len(stripped)
        s = starts[i] + prefix
        o, l = _utf16_span(text, s, s + 1)
        items.append({"type": "bold", "offset": o, "length": l})
    items.sort(key=lambda x: x["offset"])
    return text, _dump(items) if items else (text, None)


def _feedback(text: str) -> tuple[str, str | None]:
    if not text.strip():
        return text, None
    first, _, _rest = text.partition("\n")
    head = first.strip()
    hl = head.lower()
    if not (hl.startswith("верно") or hl.startswith("не совсем")):
        return text, None
    o, l = _utf16_span(text, 0, len(first))
    return text, _dump([{"type": "bold", "offset": o, "length": l}])


def _finale_bold_line(s: str) -> bool:
    t = s.lstrip()
    if t.startswith("Финал") or t.startswith("Банан") or t.startswith("Ты правильно") or t.startswith("Миссия"):
        return True
    if t and t[0] in "🥉🥈🥇🏅":
        return True
    return False


def _finale(text: str) -> tuple[str, str | None]:
    items: list[dict[str, Any]] = []
    pos = 0
    parts = text.split("\n")
    for i, line in enumerate(parts):
        if i > 0:
            pos += 1
        if _finale_bold_line(line):
            o, l = _utf16_span(text, pos, pos + len(line))
            items.append({"type": "bold", "offset": o, "length": l})
        pos += len(line)
    items.sort(key=lambda x: x["offset"])
    return text, _dump(items) if items else (text, None)
