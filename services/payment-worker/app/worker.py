"""
The core of payment-worker: long-poll the payment queue, simulate a charge,
and record the outcome on the order - guarding against double-processing
a redelivered message.
"""
import logging
import signal
import threading
import time

from app.config import settings
from app.db import get_order_status, update_order_status_if_current
from app.metrics import (
    PAYMENT_DUPLICATES_SKIPPED,
    PAYMENT_RACE_LOST,
    PAYMENTS,
    WORKER_DURATION,
    WORKER_MESSAGES,
)
from app.models import OrderStatus, PaymentRequestMessage
from app.payment_gateway import simulate_charge
from app.queue import delete_message, receive_messages

logger = logging.getLogger(settings.SERVICE_NAME)

_shutdown = threading.Event()


def _handle_signal(signum, frame) -> None:
    logger.info("Received signal %s, finishing current batch then exiting", signum)
    _shutdown.set()


def process_message(body: str) -> None:
    msg = PaymentRequestMessage.model_validate_json(body)

    # Check idempotency BEFORE charging, not after: if this message is a
    # redelivery of one we already processed, we skip it without ever
    # calling the (simulated) payment gateway again.
    current = get_order_status(msg.order_id)
    if current != OrderStatus.INVENTORY_RESERVED.value:
        PAYMENT_DUPLICATES_SKIPPED.inc()
        logger.info(
            "Order %s is already %s, skipping (likely a redelivered message)",
            msg.order_id,
            current,
        )
        return

    charged = simulate_charge(msg.amount_cents)
    new_status = (
        OrderStatus.PAYMENT_COMPLETED if charged else OrderStatus.PAYMENT_FAILED
    )

    # Belt-and-suspenders: the read above isn't atomic with this write, so
    # two concurrent redeliveries could both pass the check. The
    # conditional update here is what actually closes that race - only the
    # first writer wins, the second is discarded.
    updated = update_order_status_if_current(
        msg.order_id, new_status, expected_current_status=OrderStatus.INVENTORY_RESERVED
    )
    if not updated:
        PAYMENT_RACE_LOST.inc()
        # In a real payment system this is the case worth building a
        # reconciliation/refund path for: money may have moved (charged is
        # True) but the state transition lost the race. Flagged here as a
        # known simplification rather than solved - good material for the
        # postmortem-style write-up.
        logger.warning(
            "Order %s was updated concurrently, discarding this payment result (charged=%s)",
            msg.order_id,
            charged,
        )
        return

    PAYMENTS.labels("completed" if charged else "failed").inc()
    logger.info("Order %s: payment %s", msg.order_id, new_status.value)


def run() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    logger.info(
        "payment-worker polling %s (region=%s, failure_rate=%.0f%%)",
        settings.PAYMENT_QUEUE_URL,
        settings.AWS_REGION,
        settings.PAYMENT_FAILURE_RATE * 100,
    )

    while not _shutdown.is_set():
        messages = receive_messages()
        for message in messages:
            start = time.perf_counter()
            try:
                process_message(message["Body"])
                delete_message(message["ReceiptHandle"])
                WORKER_MESSAGES.labels("success").inc()
            except Exception:
                WORKER_MESSAGES.labels("error").inc()
                logger.exception(
                    "Failed to process message %s, leaving for redelivery",
                    message.get("MessageId"),
                )
            finally:
                WORKER_DURATION.observe(time.perf_counter() - start)

    logger.info("payment-worker shut down cleanly")
