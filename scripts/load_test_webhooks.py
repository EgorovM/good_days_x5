#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import random
import time
from dataclasses import dataclass

import httpx


@dataclass
class Stats:
    ok: int = 0
    failed: int = 0
    latencies: list[float] | None = None

    def __post_init__(self) -> None:
        if self.latencies is None:
            self.latencies = []


def _tg_start_update(uid: int, update_id: int) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": int(time.time()),
            "chat": {"id": uid, "type": "private"},
            "from": {"id": uid, "is_bot": False, "first_name": "Load"},
            "text": "/start",
            "entities": [{"offset": 0, "length": 6, "type": "bot_command"}],
        },
    }


def _vk_start_event(uid: int, cmid: int) -> dict:
    return {
        "type": "message_new",
        "object": {
            "message": {
                "id": cmid,
                "conversation_message_id": cmid,
                "date": int(time.time()),
                "peer_id": uid,
                "from_id": uid,
                "text": "старт",
            }
        },
        "group_id": 1,
        "event_id": f"load-{uid}-{cmid}",
    }


async def _post(client: httpx.AsyncClient, url: str, payload: dict, stats: Stats) -> None:
    t0 = time.perf_counter()
    try:
        resp = await client.post(url, json=payload)
        if 200 <= resp.status_code < 300:
            stats.ok += 1
        else:
            stats.failed += 1
    except httpx.HTTPError:
        stats.failed += 1
    finally:
        stats.latencies.append(time.perf_counter() - t0)


def _percentile(items: list[float], pct: float) -> float:
    if not items:
        return 0.0
    items = sorted(items)
    idx = min(len(items) - 1, int((len(items) - 1) * pct))
    return items[idx]


async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Telegram/VK webhook load. Use DRY_RUN_DELIVERY=1 for safe worker runs.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--platform", choices=("tg", "vk"), default="vk")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--secret", default="", help="Telegram secret header or VK Callback secret if configured.")
    args = parser.parse_args()

    endpoint = "/telegram/webhook" if args.platform == "tg" else "/vk/callback"
    url = args.base_url.rstrip("/") + endpoint
    headers = {}
    if args.platform == "tg" and args.secret:
        headers["X-Telegram-Bot-Api-Secret-Token"] = args.secret

    stats = Stats()
    sem = asyncio.Semaphore(args.concurrency)

    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=3.0), headers=headers) as client:
        async def one(i: int) -> None:
            async with sem:
                uid = 9_000_000 + random.randint(1, args.requests * 10)
                if args.platform == "tg":
                    payload = _tg_start_update(uid, i + 1)
                else:
                    payload = _vk_start_event(uid, i + 1)
                    if args.secret:
                        payload["secret"] = args.secret
                await _post(client, url, payload, stats)

        await asyncio.gather(*(one(i) for i in range(args.requests)))

    lats = stats.latencies or []
    print(
        f"ok={stats.ok} failed={stats.failed} "
        f"p50={_percentile(lats, 0.50)*1000:.1f}ms "
        f"p95={_percentile(lats, 0.95)*1000:.1f}ms "
        f"p99={_percentile(lats, 0.99)*1000:.1f}ms"
    )


if __name__ == "__main__":
    asyncio.run(main())
