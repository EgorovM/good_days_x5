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
    """Как финал: строки с <a …> без экранирования, остальные — esc (для ссылок в приветствии)."""
    out: list[str] = []
    for line in text.split("\n"):
        if "<a " in line:
            out.append(line)
        else:
            out.append(esc(line))
    return "\n".join(out)


def _question_html(text: str) -> str:
    lines = text.split("\n")
    if len(lines) < 3:
        return esc(text)
    title = esc(lines[0].strip())
    i = 1
    while i < len(lines) and not lines[i].strip():
        i += 1
    q_parts: list[str] = []
    while i < len(lines) and lines[i].strip():
        if lines[i].strip() == "Варианты ответа:":
            break
        if _option_line(lines[i]):
            break
        q_parts.append(lines[i])
        i += 1
    question = esc("\n".join(q_parts).strip())
    while i < len(lines) and not lines[i].strip():
        i += 1
    extra = ""
    if i < len(lines) and lines[i].strip() == "Варианты ответа:":
        extra = "\n\n<b>" + esc("Варианты ответа:") + "</b>"
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
    opts: list[str] = []
    while i < len(lines):
        raw = lines[i].strip()
        if raw:
            m = re.match(r"^([A-C]):\s*(.*)$", raw)
            if m:
                opts.append(f"<b>{esc(m.group(1))}</b>: {esc(m.group(2))}")
            else:
                opts.append(esc(lines[i]))
        i += 1
    body = f"<b>{title}</b>\n\n{question}{extra}"
    if opts:
        body += "\n\n" + "\n".join(opts)
    return body


def _option_line(s: str) -> bool:
    return bool(re.match(r"^\s*[ABC]:", s))


def _feedback_html(text: str) -> str:
    lines = text.split("\n")
    if not lines:
        return esc(text)
    first = lines[0]
    head_st = first.strip()
    low = head_st.lower()
    if low.startswith("верно") or low.startswith("не совсем"):
        tail = "\n".join(lines[1:])
        if tail.strip():
            return f"<b>{esc(first.rstrip())}</b>\n\n{esc(tail)}"
        return f"<b>{esc(first.rstrip())}</b>"
    return esc(text)


def _finale_bold_line(s: str) -> bool:
    t = s.lstrip()
    if t.startswith("Финал") or t.startswith("Банан") or t.startswith("Ты правильно") or t.startswith("Миссия"):
        return True
    if t and t[0] in "🥉🥈🥇🏅":
        return True
    return False


def _finale_html(text: str) -> str:
    out: list[str] = []
    for line in text.split("\n"):
        if "<a " in line:
            out.append(line)
        elif _finale_bold_line(line):
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
    while i < len(lines) and lines[i].strip():
        if lines[i].strip() == "Варианты ответа:":
            break
        if _option_line(lines[i]):
            break
        q_parts.append(lines[i])
        i += 1
    question = vk_plain("\n".join(q_parts).strip())
    while i < len(lines) and not lines[i].strip():
        i += 1
    extra = ""
    if i < len(lines) and lines[i].strip() == "Варианты ответа:":
        extra = "\n\n*" + vk_plain("Варианты ответа:") + "*"
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
    opts: list[str] = []
    while i < len(lines):
        raw = lines[i].strip()
        if raw:
            m = re.match(r"^([A-C]):\s*(.*)$", raw)
            if m:
                letter, body = m.group(1), m.group(2)
                opts.append(f"▸ *{letter}* — {vk_plain(body)}")
            else:
                opts.append("▸ " + vk_plain(lines[i]))
        i += 1
    body = f"*{title}*\n\n{question}{extra}"
    if opts:
        body += "\n\n" + "\n".join(opts)
    return body


def _feedback_vk(text: str) -> str:
    lines = text.split("\n")
    if not lines:
        return vk_plain(text)
    first = lines[0]
    head_st = first.strip()
    low = head_st.lower()
    if low.startswith("верно") or low.startswith("не совсем"):
        tail = "\n".join(lines[1:])
        head = vk_plain(first.rstrip())
        if tail.strip():
            return f"*{head}*\n{vk_plain(tail)}"
        return f"*{head}*"
    return vk_plain(text)


def _finale_vk(text: str) -> str:
    out: list[str] = []
    for line in text.split("\n"):
        if _finale_bold_line(line):
            out.append(f"*{vk_plain(line)}*")
        else:
            out.append(vk_plain(line))
    return "\n".join(out)
