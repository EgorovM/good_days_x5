from __future__ import annotations

from app.business_stats import BusinessStatsStore, MemoryBusinessStats
from app.config import Settings
from app.media_cache import MediaCache, MemoryMediaCache
from app.outbox import MemoryOutbox, Outbox
from app.session_store import MemorySessionStore, SessionStore

settings: Settings | None = None
session_store: SessionStore = MemorySessionStore()
outbox: Outbox = MemoryOutbox()
media_cache: MediaCache = MemoryMediaCache()
business_stats: BusinessStatsStore = MemoryBusinessStats()
