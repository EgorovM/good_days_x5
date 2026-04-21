from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.scenario_loader import load_game


@dataclass
class Segment:
    """Один шаг отправки в чат."""

    text: str | None = None
    image: str | None = None  # имя файла в static/images
    options: list[tuple[str, str]] | None = None  # (id A/B/C, короткий текст для кнопки)
    kind: str = "plain"  # plain | intro | question | feedback | finale — для HTML (TG + VK)


@dataclass
class GameSession:
    score: int = 0
    q_index: int = 0  # текущий вопрос 0..7; после финала не используется
    finished: bool = False


def pick_title(titles: list[dict[str, Any]], score: int) -> dict[str, Any]:
    for row in titles:
        if row["min"] <= score <= row["max"]:
            return row
    return titles[-1]


def format_question_block(q: dict[str, Any]) -> str:
    lines = [q["stage_title"], "", q["question"], ""]
    for opt in q["options"]:
        lines.append(f"{opt['id']}) {opt['text']}")
    return "\n".join(lines)


def start_game() -> tuple[GameSession, list[Segment]]:
    game = load_game()
    session = GameSession()
    segments: list[Segment] = [Segment(text=game["intro"]["text"], kind="intro")]
    if game["intro"].get("image"):
        segments.append(Segment(image=game["intro"]["image"], kind="plain"))
    segments.extend(question_segments(game["questions"][0]))
    return session, segments


def question_segments(question: dict[str, Any]) -> list[Segment]:
    """Картинка (если есть) отдельно, затем текст с вариантами и клавиатура."""
    segs: list[Segment] = []
    if question.get("image"):
        # Только картинка: заголовок этапа уже в format_question_block во втором сообщении
        segs.append(Segment(image=question["image"], kind="plain"))
    body = format_question_block(question)
    opts = [(o["id"], o["id"]) for o in question["options"]]
    segs.append(Segment(text=body, options=opts, kind="question"))
    return segs


def apply_answer(session: GameSession, option_id: str) -> tuple[GameSession, list[Segment]]:
    if session.finished:
        return session, [Segment(text="Игра уже завершена. Нажми /start чтобы пройти заново.", kind="plain")]

    game = load_game()
    q = game["questions"][session.q_index]
    chosen = next((o for o in q["options"] if o["id"] == option_id), None)
    if chosen is None:
        return session, [Segment(text="Не понял ответ. Выбери вариант на клавиатуре.", kind="plain")]

    out: list[Segment] = [Segment(text=chosen["feedback"], kind="feedback")]
    if chosen["correct"]:
        session.score += 1

    session.q_index += 1
    if session.q_index < len(game["questions"]):
        out.extend(question_segments(game["questions"][session.q_index]))
    else:
        out.extend(finale_segments(session.score))
        session.finished = True
    return session, out


def finale_segments(score: int) -> list[Segment]:
    game = load_game()
    fin = game["finale"]
    title = pick_title(game["titles"], score)
    lines = [
        fin["success_intro"],
        "",
        fin["score_line"].format(score=score),
        "",
        f"🏅 {title['title']}",
        title["subtitle"],
        "",
        fin["outro"],
    ]
    segs = [Segment(text="\n".join(lines), kind="finale")]
    if title.get("image"):
        segs.append(Segment(image=title["image"], kind="plain"))
    return segs


def reset_session() -> GameSession:
    return GameSession()
