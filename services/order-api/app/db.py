"""
DynamoDB access layer.

Table schema (created by Terraform in Phase 1, referenced here only):
  - Partition key: order_id (S)
  - No sort key needed - each order is a single item that gets updated
    in place as it moves through PENDING -> INVENTORY_RESERVED -> ... etc.
"""
import logging

import boto3
from botocore.exceptions import ClientError

from app.config import settings
from app.models import Order

logger = logging.getLogger(settings.SERVICE_NAME)

_dynamodb = boto3.resource("dynamodb", region_name=settings.AWS_REGION)
_table = _dynamodb.Table(settings.ORDERS_TABLE_NAME)


def put_order(order: Order) -> None:
    try:
        _table.put_item(Item=order.model_dump())
    except ClientError:
        logger.exception("Failed to write order %s to DynamoDB", order.order_id)
        raise


def get_order(order_id: str) -> dict | None:
    try:
        response = _table.get_item(Key={"order_id": order_id})
    except ClientError:
        logger.exception("Failed to read order %s from DynamoDB", order_id)
        raise
    return response.get("Item")
