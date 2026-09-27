"""
DynamoDB access layer.

Two tables are involved:
  - orders (order-platform-orders): same table order-api writes to.
    inventory-worker only ever updates the `status`/`updated_at` fields
    of an existing row here.
  - inventory (order-platform-inventory): partition key `sku`, attribute
    `quantity_available` (Number). Reservation uses a conditional update
    so concurrent workers can never oversell the same SKU.
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
_inventory_table = _dynamodb.Table(settings.INVENTORY_TABLE_NAME)


def reserve_item(sku: str, quantity: int) -> bool:
    """Atomically decrement stock if enough is available. Returns False
    (instead of raising) when there isn't enough stock, so the caller can
    treat it as a normal business outcome rather than an error."""
    try:
        _inventory_table.update_item(
            Key={"sku": sku},
            UpdateExpression="SET quantity_available = quantity_available - :q",
            ConditionExpression="quantity_available >= :q",
            ExpressionAttributeValues={":q": quantity},
        )
        return True
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return False
        logger.exception("Failed to reserve sku=%s qty=%s", sku, quantity)
        raise


def release_item(sku: str, quantity: int) -> None:
    """Compensating action: give back stock reserved earlier in the same
    order after a later item in that order failed to reserve."""
    try:
        _inventory_table.update_item(
            Key={"sku": sku},
            UpdateExpression="SET quantity_available = quantity_available + :q",
            ExpressionAttributeValues={":q": quantity},
        )
    except ClientError:
        logger.exception("Failed to release sku=%s qty=%s", sku, quantity)
        raise


def update_order_status(order_id: str, status: OrderStatus) -> None:
    try:
        _orders_table.update_item(
            Key={"order_id": order_id},
            UpdateExpression="SET #s = :s, updated_at = :u",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": status.value,
                ":u": datetime.now(timezone.utc).isoformat(),
            },
        )
    except ClientError:
        logger.exception("Failed to update order %s to %s", order_id, status)
        raise
