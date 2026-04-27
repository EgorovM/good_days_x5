from __future__ import annotations

import time
from typing import Any, Protocol

from redis.asyncio import Redis


def _safe_pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


class BusinessStatsStore(Protocol):
    async def inc_start(self, platform: str, *, event_key: str | None = None) -> None: ...

    async def inc_answer(
        self,
        platform: str,
        *,
        q_index: int,
        option_id: str,
        correct: bool,
        event_key: str | None = None,
    ) -> None: ...

    async def inc_finish(
        self,
        platform: str,
        *,
        score: int,
        title: str,
        event_key: str | None = None,
    ) -> None: ...

    async def report(self) -> dict[str, Any]: ...

    async def ready(self) -> bool: ...


class MemoryBusinessStats:
    def __init__(self) -> None:
        self.starts = {"total": 0, "tg": 0, "vk": 0}
        self.answers_total = 0
        self.answers_correct = 0
        self.finishes = {"total": 0, "tg": 0, "vk": 0}
        self.by_q: dict[int, dict[str, int]] = {}
        self.by_q_opt: dict[int, dict[str, int]] = {}
        self.scores: dict[int, int] = {}
        self.titles: dict[str, int] = {}
        self._dedupe: dict[str, float] = {}

    def _seen(self, event_key: str | None) -> bool:
        if not event_key:
            return False
        now = time.monotonic()
        if len(self._dedupe) > 50_000:
            cutoff = now - 7 * 86_400
            self._dedupe = {k: v for k, v in self._dedupe.items() if v > cutoff}
        if event_key in self._dedupe:
            return True
        self._dedupe[event_key] = now
        return False

    async def inc_start(self, platform: str, *, event_key: str | None = None) -> None:
        if self._seen(event_key):
            return
        self.starts["total"] += 1
        self.starts[platform] = self.starts.get(platform, 0) + 1

    async def inc_answer(
        self,
        platform: str,
        *,
        q_index: int,
        option_id: str,
        correct: bool,
        event_key: str | None = None,
    ) -> None:
        if self._seen(event_key):
            return
        self.answers_total += 1
        if correct:
            self.answers_correct += 1
        q = self.by_q.setdefault(q_index, {"total": 0, "correct": 0})
        q["total"] += 1
        if correct:
            q["correct"] += 1
        self.by_q_opt.setdefault(q_index, {})
        self.by_q_opt[q_index][option_id] = self.by_q_opt[q_index].get(option_id, 0) + 1

    async def inc_finish(
        self,
        platform: str,
        *,
        score: int,
        title: str,
        event_key: str | None = None,
    ) -> None:
        if self._seen(event_key):
            return
        self.finishes["total"] += 1
        self.finishes[platform] = self.finishes.get(platform, 0) + 1
        self.scores[score] = self.scores.get(score, 0) + 1
        self.titles[title] = self.titles.get(title, 0) + 1

    async def report(self) -> dict[str, Any]:
        started_total = int(self.starts.get("total", 0))
        finished_total = int(self.finishes.get("total", 0))
        funnel = {
            "started_total": started_total,
            "finished_total": finished_total,
            "completion_rate_pct": _safe_pct(finished_total, started_total),
        }
        q_rows = []
        for q in sorted(self.by_q.keys()):
            total = int(self.by_q[q].get("total", 0))
            correct = int(self.by_q[q].get("correct", 0))
            q_rows.append(
                {
                    "q": q,
                    "answers_total": total,
                    "answers_correct": correct,
                    "accuracy_pct": _safe_pct(correct, total),
                    "options": self.by_q_opt.get(q, {}),
                }
            )
        return {
            "funnel": funnel,
            "starts_by_platform": {"tg": int(self.starts.get("tg", 0)), "vk": int(self.starts.get("vk", 0))},
            "answers_total": int(self.answers_total),
            "answers_correct": int(self.answers_correct),
            "answers_accuracy_pct": _safe_pct(self.answers_correct, self.answers_total),
            "questions": q_rows,
            "finishes_by_platform": {"tg": int(self.finishes.get("tg", 0)), "vk": int(self.finishes.get("vk", 0))},
            "scores": {str(k): v for k, v in sorted(self.scores.items())},
            "titles": dict(sorted(self.titles.items())),
        }

    async def ready(self) -> bool:
        return True


class RedisBusinessStats:
    def __init__(self, redis: Redis, *, prefix: str = "good_days:biz", dedupe_ttl_seconds: int = 7 * 86_400) -> None:
        self.redis = redis
        self.prefix = prefix
        self.dedupe_ttl_seconds = dedupe_ttl_seconds

    async def _is_new(self, event_key: str | None) -> bool:
        if not event_key:
            return True
        key = f"{self.prefix}:dedupe:{event_key}"
        return bool(await self.redis.set(key, "1", nx=True, ex=self.dedupe_ttl_seconds))

    async def inc_start(self, platform: str, *, event_key: str | None = None) -> None:
        if not await self._is_new(event_key):
            return
        key = f"{self.prefix}:starts"
        await self.redis.hincrby(key, "total", 1)
        await self.redis.hincrby(key, platform, 1)

    async def inc_answer(
        self,
        platform: str,
        *,
        q_index: int,
        option_id: str,
        correct: bool,
        event_key: str | None = None,
    ) -> None:
        if not await self._is_new(event_key):
            return
        key = f"{self.prefix}:answers"
        await self.redis.hincrby(key, "total", 1)
        await self.redis.hincrby(key, f"platform:{platform}:total", 1)
        await self.redis.hincrby(key, f"q:{q_index}:total", 1)
        await self.redis.hincrby(key, f"q:{q_index}:opt:{option_id}", 1)
        if correct:
            await self.redis.hincrby(key, "correct", 1)
            await self.redis.hincrby(key, f"platform:{platform}:correct", 1)
            await self.redis.hincrby(key, f"q:{q_index}:correct", 1)

    async def inc_finish(
        self,
        platform: str,
        *,
        score: int,
        title: str,
        event_key: str | None = None,
    ) -> None:
        if not await self._is_new(event_key):
            return
        key = f"{self.prefix}:finishes"
        await self.redis.hincrby(key, "total", 1)
        await self.redis.hincrby(key, platform, 1)
        await self.redis.hincrby(f"{self.prefix}:scores", str(score), 1)
        await self.redis.hincrby(f"{self.prefix}:titles", title, 1)

    async def report(self) -> dict[str, Any]:
        starts = await self.redis.hgetall(f"{self.prefix}:starts")
        answers = await self.redis.hgetall(f"{self.prefix}:answers")
        finishes = await self.redis.hgetall(f"{self.prefix}:finishes")
        scores = await self.redis.hgetall(f"{self.prefix}:scores")
        titles = await self.redis.hgetall(f"{self.prefix}:titles")

        started_total = int(starts.get("total", 0))
        finished_total = int(finishes.get("total", 0))
        answers_total = int(answers.get("total", 0))
        answers_correct = int(answers.get("correct", 0))

        q_indices = set()
        for field in answers.keys():
            if field.startswith("q:"):
                parts = field.split(":")
                if len(parts) >= 3 and parts[1].isdigit():
                    q_indices.add(int(parts[1]))

        questions = []
        for q in sorted(q_indices):
            total = int(answers.get(f"q:{q}:total", 0))
            correct = int(answers.get(f"q:{q}:correct", 0))
            opts = {
                k.split(":")[-1]: int(v)
                for k, v in answers.items()
                if k.startswith(f"q:{q}:opt:")
            }
            questions.append(
                {
                    "q": q,
                    "answers_total": total,
                    "answers_correct": correct,
                    "accuracy_pct": _safe_pct(correct, total),
                    "options": dict(sorted(opts.items())),
                }
            )

        return {
            "funnel": {
                "started_total": started_total,
                "finished_total": finished_total,
                "completion_rate_pct": _safe_pct(finished_total, started_total),
            },
            "starts_by_platform": {"tg": int(starts.get("tg", 0)), "vk": int(starts.get("vk", 0))},
            "answers_total": answers_total,
            "answers_correct": answers_correct,
            "answers_accuracy_pct": _safe_pct(answers_correct, answers_total),
            "questions": questions,
            "finishes_by_platform": {"tg": int(finishes.get("tg", 0)), "vk": int(finishes.get("vk", 0))},
            "scores": {k: int(v) for k, v in sorted(scores.items(), key=lambda kv: int(kv[0]))},
            "titles": {k: int(v) for k, v in sorted(titles.items())},
        }

    async def ready(self) -> bool:
        return bool(await self.redis.ping())
