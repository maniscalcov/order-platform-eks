"""
Prometheus metrics for inventory-worker, served on the existing health port
(8080) at /metrics and scraped via a PodMonitor - workers have no Service.
"""
from prometheus_client import Counter, Histogram

WORKER_MESSAGES = Counter(
    "worker_messages_total",
    "SQS messages handled, by outcome. 'error' = left on the queue for "
    "redelivery (repeated errors end up in the DLQ).",
    ["outcome"],
)
WORKER_DURATION = Histogram(
    "worker_message_duration_seconds",
    "Time to process one SQS message end to end (includes AWS calls).",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)

INVENTORY_RESERVATIONS = Counter(
    "inventory_reservations_total",
    "Order-level reservation results: reserved = all items held, "
    "out_of_stock = at least one item unavailable (earlier items released).",
    ["result"],
)
