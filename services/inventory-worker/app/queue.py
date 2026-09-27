"""
SQS access layer.

inventory-worker is the only service that both consumes and produces:
it polls the inventory queue and, on success, publishes to the payment
queue for payment-worker to pick up.
"""
import logging

import boto3
from botocore.exceptions import ClientError

from app.config import settings
from app.models import PaymentRequestMessage

logger = logging.getLogger(settings.SERVICE_NAME)

_sqs = boto3.client("sqs", region_name=settings.AWS_REGION)


def receive_messages() -> list[dict]:
    response = _sqs.receive_message(
        QueueUrl=settings.INVENTORY_QUEUE_URL,
        MaxNumberOfMessages=settings.MAX_MESSAGES_PER_POLL,
        WaitTimeSeconds=settings.POLL_WAIT_TIME_SECONDS,
    )
    return response.get("Messages", [])


def delete_message(receipt_handle: str) -> None:
    try:
        _sqs.delete_message(
            QueueUrl=settings.INVENTORY_QUEUE_URL, ReceiptHandle=receipt_handle
        )
    except ClientError:
        logger.exception("Failed to delete message from inventory queue")
        raise


def publish_payment_request(message: PaymentRequestMessage) -> None:
    try:
        _sqs.send_message(
            QueueUrl=settings.PAYMENT_QUEUE_URL,
            MessageBody=message.model_dump_json(),
        )
    except ClientError:
        logger.exception(
            "Failed to publish payment request for order %s", message.order_id
        )
        raise
