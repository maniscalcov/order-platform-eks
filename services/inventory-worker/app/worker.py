"""
The core of inventory-worker: long-poll the inventory queue, try to reserve
stock for every item on the order, and hand off to payment-worker on
success.

Reservation is all-or-nothing per order. If any item runs out mid-way, the
items already reserved for that same order are released before marking the
order INVENTORY_FAILED - this keeps a partial failure from silently locking
up stock the customer will never pay for.
"""
import logging
import signal
import threading

from app.config import settings
from app.db import release_item, reserve_item, update_order_status
from app.models import InventoryReservationMessage, OrderStatus, PaymentRequestMessage
from app.queue import delete_message, publish_payment_request, receive_messages

logger = logging.getLogger(settings.SERVICE_NAME)

_shutdown = threading.Event()


def _handle_signal(signum, frame) -> None:
    logger.info("Received signal %s, finishing current batch then exiting", signum)
    _shutdown.set()


def process_message(body: str) -> None:
    msg = InventoryReservationMessage.model_validate_json(body)
    reserved_items = []
    failed_sku = None

    for item in msg.items:
        if reserve_item(item.sku, item.quantity):
            reserved_items.append(item)
        else:
            failed_sku = item.sku
            break

    if failed_sku is not None:
        for item in reserved_items:
            release_item(item.sku, item.quantity)
        update_order_status(msg.order_id, OrderStatus.INVENTORY_FAILED)
        logger.warning(
            "Order %s failed to reserve sku=%s, released %d earlier reservation(s)",
            msg.order_id,
            failed_sku,
            len(reserved_items),
        )
        return

    update_order_status(msg.order_id, OrderStatus.INVENTORY_RESERVED)
    amount_cents = sum(i.quantity * i.unit_price_cents for i in msg.items)
    publish_payment_request(
        PaymentRequestMessage(
            order_id=msg.order_id,
            customer_id=msg.customer_id,
            amount_cents=amount_cents,
        )
    )
    logger.info(
        "Order %s: inventory reserved, handed off to payment queue", msg.order_id
    )


def run() -> None:
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    logger.info(
        "inventory-worker polling %s (region=%s)",
        settings.INVENTORY_QUEUE_URL,
        settings.AWS_REGION,
    )

    while not _shutdown.is_set():
        messages = receive_messages()
        for message in messages:
            try:
                process_message(message["Body"])
                delete_message(message["ReceiptHandle"])
            except Exception:
                # Deliberately don't delete the message on failure - it
                # becomes visible again after the queue's visibility
                # timeout and gets retried. After N receives, the queue's
                # redrive policy (define this in the Phase 1 Terraform
                # alongside the queue) routes it to a dead-letter queue
                # instead of retrying forever.
                logger.exception(
                    "Failed to process message %s, leaving for redelivery",
                    message.get("MessageId"),
                )

    logger.info("inventory-worker shut down cleanly")
