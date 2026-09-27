"""
The core of payment-worker: long-poll the payment queue, simulate a charge,
and record the outcome on the order - guarding against double-processing
a redelivered message.
"""
import logging
import signal
import threading

from app.config import settings
from app.db import get_order_status, update_order_status_if_current
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
            try:
                process_message(message["Body"])
                delete_message(message["ReceiptHandle"])
            except Exception:
                logger.exception(
                    "Failed to process message %s, leaving for redelivery",
                    message.get("MessageId"),
                )

    logger.info("payment-worker shut down cleanly")
