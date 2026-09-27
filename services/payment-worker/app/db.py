"""
DynamoDB access layer.

payment-worker only touches the orders table, and only ever transitions an
order out of INVENTORY_RESERVED. The conditional update in
update_order_status_if_current is what makes this safe under SQS's
at-least-once delivery: if the same message is redelivered and processed
twice (including concurrently, by two pod replicas), only the first write
wins - the second gets ConditionalCheckFailedException and is discarded
rather than double-processing the order.
"""
import logging
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from app.config import settings
from app.models import OrderStatus

logger = logging.getLogger(settings.SERVICE_NAME)

_dynamodb = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
_orders_table = _dynamodb.Table(settings.ORDERS_TABLE_NAME)


def get_order_status(order_id: str) -> str | None:
    try:
        response = _orders_table.get_item(
            Key={"order_id": order_id},
            ProjectionExpression="#s",
            ExpressionAttributeNames={"#s": "status"},
        )
    except ClientError:
        logger.exception("Failed to read status for order %s", order_id)
        raise
    item = response.get("Item")
    return item["status"] if item else None


def update_order_status_if_current(
    order_id: str, new_status: OrderStatus, expected_current_status: OrderStatus
) -> bool:
    try:
        _orders_table.update_item(
            Key={"order_id": order_id},
            UpdateExpression="SET #s = :new, updated_at = :u",
            ConditionExpression="#s = :expected",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":new": new_status.value,
                ":expected": expected_current_status.value,
                ":u": datetime.now(timezone.utc).isoformat(),
            },
        )
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        logger.exception("Failed to update order %s to %s", order_id, new_status)
        raise
