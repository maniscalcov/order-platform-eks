"""
Prometheus metrics for payment-worker, served on the existing health port
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

PAYMENTS = Counter(
    "payments_total",
    "Simulated charges by result (failed should hover near PAYMENT_FAILURE_RATE).",
    ["result"],
)
PAYMENT_DUPLICATES_SKIPPED = Counter(
    "payment_duplicates_skipped_total",
    "Redelivered messages skipped by the idempotency check (no second charge).",
)
PAYMENT_RACE_LOST = Counter(
    "payment_race_lost_total",
    "Charges whose status write lost the conditional-update race. Non-zero "
    "means money may have moved without a recorded state change.",
)
