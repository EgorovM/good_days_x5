from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

SCENARIO_DIR = Path(__file__).resolve().parent / "scenario"


@lru_cache
def load_game() -> dict:
    intro = _read_json(SCENARIO_DIR / "intro.json")
    titles = _read_json(SCENARIO_DIR / "titles.json")
    finale = _read_json(SCENARIO_DIR / "finale.json")
    questions_dir = SCENARIO_DIR / "questions"
    questions = []
    for i in range(1, 9):
        questions.append(_read_json(questions_dir / f"{i:02d}.json"))
    return {"intro": intro, "titles": titles, "finale": finale, "questions": questions}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
