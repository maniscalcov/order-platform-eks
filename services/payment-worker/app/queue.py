"""
SQS access layer. payment-worker is a pure consumer - it's the last stop
in the saga, so there's no downstream queue to publish to.
"""
import logging

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(settings.SERVICE_NAME)

_sqs = boto3.client("sqs", region_name=settings.AWS_REGION)


def receive_messages() -> list[dict]:
    response = _sqs.receive_message(
        QueueUrl=settings.PAYMENT_QUEUE_URL,
        MaxNumberOfMessages=settings.MAX_MESSAGES_PER_POLL,
        WaitTimeSeconds=settings.POLL_WAIT_TIME_SECONDS,
    )
    return response.get("Messages", [])


def delete_message(receipt_handle: str) -> None:
    try:
        _sqs.delete_message(
            QueueUrl=settings.PAYMENT_QUEUE_URL, ReceiptHandle=receipt_handle
        )
    except ClientError:
        logger.exception("Failed to delete message from payment queue")
        raise
