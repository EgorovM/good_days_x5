from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.scenario_loader import load_game


@dataclass
class Segment:
    """Один шаг отправки в чат."""

    text: str | None = None
    image: str | None = None  # имя файла в static/images
    options: list[tuple[str, str]] | None = None  # (callback id: ans:A | nav:go | nav:next, подпись кнопки)
    kind: str = "plain"  # plain | intro | question | feedback | finale — для HTML (TG + VK)


@dataclass
class GameSession:
    score: int = 0
    q_index: int = 0  # текущий вопрос 0..7; после ответа на последний — 8 и finished
    finished: bool = False
    intro_pending: bool = False  # ждём «Поехали!»
    continue_pending: bool = False  # ждём «Следующий этап» / «Финальный этап»


def pick_title(titles: list[dict[str, Any]], score: int) -> dict[str, Any]:
    for row in titles:
        if row["min"] <= score <= row["max"]:
            return row
    return titles[-1]


def format_question_block(q: dict[str, Any]) -> str:
    lines = [q["stage_title"], "", q["question"], "", "Варианты ответа:", ""]
    for opt in q["options"]:
        lines.append(f"{opt['id']}: {opt['text']}")
    return "\n".join(lines)


def start_game() -> tuple[GameSession, list[Segment]]:
    game = load_game()
    intro = game["intro"]
    session = GameSession(
        intro_pending=True,
        continue_pending=False,
        q_index=0,
        score=0,
        finished=False,
    )
    seg = Segment(
        text=intro["text"],
        image=intro.get("image"),
        options=[("nav:go", "Поехали!")],
        kind="plain",
    )
    return session, [seg]


def question_segments(question: dict[str, Any]) -> list[Segment]:
    """Одно сообщение: картинка (если есть) + текст с вариантами и клавиатура A/B/C."""
    body = format_question_block(question)
    opts = [(f"ans:{o['id']}", o["id"]) for o in question["options"]]
    return [Segment(text=body, image=question.get("image"), options=opts, kind="question")]


def acknowledge_intro(session: GameSession) -> tuple[GameSession, list[Segment]]:
    if not session.intro_pending:
        return session, [Segment(text="Квест уже идёт. Ответь на вопрос или нажми «старт» заново.", kind="plain")]
    session.intro_pending = False
    session.continue_pending = False
    game = load_game()
    return session, question_segments(game["questions"][0])


def continue_stage(session: GameSession) -> tuple[GameSession, list[Segment]]:
    if session.finished:
        return session, [Segment(text="Игра завершена. Нажми /start чтобы пройти заново.", kind="plain")]
    if session.intro_pending:
        return session, [Segment(text="Сначала нажми «Поехали!»", kind="plain")]
    if not session.continue_pending:
        return session, [Segment(text="Сначала выбери ответ A, B или C.", kind="plain")]
    session.continue_pending = False
    session.q_index += 1
    game = load_game()
    n = len(game["questions"])
    if session.q_index < n:
        return session, question_segments(game["questions"][session.q_index])
    return session, [Segment(text="Нет следующего этапа.", kind="plain")]


def apply_answer(session: GameSession, option_id: str) -> tuple[GameSession, list[Segment]]:
    if session.finished:
        return session, [Segment(text="Игра уже завершена. Нажми /start чтобы пройти заново.", kind="plain")]

    if session.intro_pending:
        return session, [
            Segment(text="Чтобы начать квест, нажми кнопку «Поехали!» под приветствием.", kind="plain")
        ]

    if session.continue_pending:
        return session, [
            Segment(
                text="Сначала нажми «Следующий этап» или «Финальный этап», чтобы перейти дальше.",
                kind="plain",
            )
        ]

    game = load_game()
    q = game["questions"][session.q_index]
    chosen = next((o for o in q["options"] if o["id"] == option_id), None)
    if chosen is None:
        return session, [Segment(text="Не понял ответ. Выбери вариант на клавиатуре.", kind="plain")]

    if chosen["correct"]:
        session.score += 1

    feedback = Segment(text=chosen["feedback"], kind="feedback")

    if session.q_index < 7:
        session.continue_pending = True
        label = "Финальный этап" if session.q_index == 6 else "Следующий этап"
        feedback.options = [("nav:next", label)]
        return session, [feedback]

    session.q_index = 8
    session.finished = True
    return session, [feedback, *finale_segments(session.score)]


def finale_segments(score: int) -> list[Segment]:
    game = load_game()
    fin = game["finale"]
    title = pick_title(game["titles"], score)
    lines = [
        fin["success_intro"],
        "",
        fin["score_line"].format(score=score),
        "",
        title["title"],
        title["subtitle"],
        "",
        fin["outro"],
    ]
    return [Segment(text="\n".join(lines), image=title.get("image"), kind="finale")]


def title_for_score(score: int) -> str:
    game = load_game()
    title = pick_title(game["titles"], score)
    return str(title["title"])


def reset_session() -> GameSession:
    return GameSession()
