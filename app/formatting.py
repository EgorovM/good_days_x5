from __future__ import annotations

import html
import re


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def vk_plain(s: str) -> str:
    """Убирает символы, ломающие VK markdown (*жирный*, _курсив_, ссылки [...|...])."""
    return s.replace("*", "∗").replace("_", "ˍ").replace("[", "［").replace("]", "］")


def format_segment_vk(text: str, kind: str) -> str:
    """Разметка для VK: messages.send с format=1 (markdown ВКонтакте)."""
    if kind == "plain":
        return vk_plain(text)
    if kind == "intro":
        return _intro_vk(text)
    if kind == "question":
        return _question_vk(text)
    if kind == "feedback":
        return _feedback_vk(text)
    if kind == "finale":
        return _finale_vk(text)
    return vk_plain(text)


def format_segment_html(text: str, kind: str) -> str:
    if kind == "plain":
        return esc(text)
    if kind == "intro":
        return _intro_html(text)
    if kind == "question":
        return _question_html(text)
    if kind == "feedback":
        return _feedback_html(text)
    if kind == "finale":
        return _finale_html(text)
    return esc(text)


def _intro_html(text: str) -> str:
    lines = text.split("\n")
    if not lines:
        return esc(text)
    first = esc(lines[0])
    rest = "\n".join(esc(ln) for ln in lines[1:])
    if rest.strip():
        return f"<b>{first}</b>\n{rest}"
    return f"<b>{first}</b>"


def _question_html(text: str) -> str:
    lines = text.split("\n")
    if len(lines) < 3:
        return esc(text)
    title = esc(lines[0].strip())
    i = 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    q_parts: list[str] = []
    while i < len(lines) and lines[i].strip() and not _option_line(lines[i]):
        q_parts.append(lines[i])
        i += 1
    question = esc("\n".join(q_parts).strip())
    while i < len(lines) and not lines[i].strip():
        i += 1
    opts: list[str] = []
    while i < len(lines):
        raw = lines[i].strip()
        if raw:
            m = re.match(r"^([A-C])\)\s*(.*)$", raw)
            if m:
                opts.append(f"<b>{esc(m.group(1))}</b>) {esc(m.group(2))}")
            else:
                opts.append(esc(lines[i]))
        i += 1
    body = f"<b>{title}</b>\n\n{question}"
    if opts:
        body += "\n\n" + "\n".join(opts)
    return body


def _option_line(s: str) -> bool:
    return bool(re.match(r"^\s*[ABC]\)", s))


def _feedback_html(text: str) -> str:
    t = text.strip()
    low = t.lower()
    if low.startswith("верно"):
        parts = t.split(None, 1)
        head = parts[0]
        tail = parts[1] if len(parts) > 1 else ""
        if tail:
            return f"<b>{esc(head)}</b> {esc(tail)}"
        return f"<b>{esc(head)}</b>"
    return esc(t)


def _finale_html(text: str) -> str:
    out: list[str] = []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("Миссия") or s.startswith("Ты правильно") or s.startswith("🏅"):
            out.append(f"<b>{esc(line)}</b>")
        else:
            out.append(esc(line))
    return "\n".join(out)


def _intro_vk(text: str) -> str:
    lines = text.split("\n")
    if not lines:
        return vk_plain(text)
    first = vk_plain(lines[0])
    rest = "\n".join(vk_plain(ln) for ln in lines[1:])
    if rest.strip():
        return f"*{first}*\n{rest}"
    return f"*{first}*"


def _question_vk(text: str) -> str:
    lines = text.split("\n")
    if len(lines) < 3:
        return vk_plain(text)
    title = vk_plain(lines[0].strip())
    i = 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    q_parts: list[str] = []
    while i < len(lines) and lines[i].strip() and not _option_line(lines[i]):
        q_parts.append(lines[i])
        i += 1
    question = vk_plain("\n".join(q_parts).strip())
    while i < len(lines) and not lines[i].strip():
        i += 1
    opts: list[str] = []
    while i < len(lines):
        raw = lines[i].strip()
        if raw:
            m = re.match(r"^([A-C])\)\s*(.*)$", raw)
            if m:
                letter, body = m.group(1), m.group(2)
                opts.append(f"▸ *{letter}* — {vk_plain(body)}")
            else:
                opts.append("▸ " + vk_plain(lines[i]))
        i += 1
    body = f"*{title}*\n\n{question}"
    if opts:
        body += "\n\n" + "\n".join(opts)
    return body


def _feedback_vk(text: str) -> str:
    t = text.strip()
    low = t.lower()
    if low.startswith("верно"):
        parts = t.split(None, 1)
        head = vk_plain(parts[0])
        tail = vk_plain(parts[1]) if len(parts) > 1 else ""
        if tail:
            return f"*{head}* {tail}"
        return f"*{head}*"
    return vk_plain(t)


def _finale_vk(text: str) -> str:
    out: list[str] = []
    for line in text.split("\n"):
        s = line.strip()
        if s.startswith("Миссия") or s.startswith("Ты правильно") or s.startswith("🏅"):
            out.append(f"*{vk_plain(line)}*")
        else:
            out.append(vk_plain(line))
    return "\n".join(out)
