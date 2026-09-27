"""
SQS producer.

order-api's only responsibility on the messaging side is to publish an
InventoryReservationMessage after it has durably written the order to
DynamoDB. It never reads from any queue.
"""
import logging

import boto3
from botocore.exceptions import ClientError

from app.config import settings
from app.models import InventoryReservationMessage

logger = logging.getLogger(settings.SERVICE_NAME)

_sqs = boto3.client("sqs", region_name=settings.AWS_REGION)


def publish_inventory_reservation(message: InventoryReservationMessage) -> None:
    try:
        _sqs.send_message(
            QueueUrl=settings.INVENTORY_QUEUE_URL,
            MessageBody=message.model_dump_json(),
        )
    except ClientError:
        logger.exception(
            "Failed to publish inventory reservation for order %s",
            message.order_id,
        )
        raise
