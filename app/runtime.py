from __future__ import annotations

from app.config import Settings
from app.game_engine import GameSession

settings: Settings | None = None
tg_sessions: dict[int, GameSession] = {}
vk_sessions: dict[int, GameSession] = {}
