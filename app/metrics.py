from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.responses import Response

WEBHOOK_EVENTS = Counter(
    "good_days_webhook_events_total",
    "Incoming webhook events",
    ("platform", "event_type", "status"),
)

WEBHOOK_LATENCY = Histogram(
    "good_days_webhook_latency_seconds",
    "Webhook processing latency before ack",
    ("platform", "event_type"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

SEND_EVENTS = Counter(
    "good_days_send_events_total",
    "Outbound send events",
    ("platform", "status"),
)

SEND_LATENCY = Histogram(
    "good_days_send_latency_seconds",
    "Outbound send latency",
    ("platform",),
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)

QUEUE_SIZE = Gauge(
    "good_days_outbox_queue_size",
    "Approximate outbox queue size",
)

RETRY_EVENTS = Counter(
    "good_days_outbox_retries_total",
    "Outbox retry attempts",
    ("platform",),
)


def metrics_response() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
