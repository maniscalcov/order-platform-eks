"""
Data contracts for the order flow.

These shapes are the "API" between order-api, inventory-worker, and
payment-worker even though they never call each other directly - they only
communicate through DynamoDB state and SQS messages. Getting this file right
first is what makes the two workers straightforward to write afterward.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


class OrderStatus(str, Enum):
    PENDING = "PENDING"                        # order-api just created it
    INVENTORY_RESERVED = "INVENTORY_RESERVED"  # inventory-worker succeeded
    INVENTORY_FAILED = "INVENTORY_FAILED"      # inventory-worker couldn't reserve stock
    PAYMENT_COMPLETED = "PAYMENT_COMPLETED"    # payment-worker succeeded
    PAYMENT_FAILED = "PAYMENT_FAILED"          # payment-worker declined/errored


class OrderItem(BaseModel):
    sku: str
    quantity: int = Field(gt=0)
    unit_price_cents: int = Field(gt=0)


class OrderCreateRequest(BaseModel):
    customer_id: str
    items: List[OrderItem]

    @field_validator("items")
    @classmethod
    def must_have_items(cls, v: List[OrderItem]) -> List[OrderItem]:
        if not v:
            raise ValueError("order must contain at least one item")
        return v


class Order(BaseModel):
    order_id: str = Field(default_factory=lambda: str(uuid4()))
    customer_id: str
    items: List[OrderItem]
    total_amount_cents: int
    status: OrderStatus = OrderStatus.PENDING
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def from_request(cls, req: OrderCreateRequest) -> "Order":
        total = sum(i.quantity * i.unit_price_cents for i in req.items)
        return cls(
            customer_id=req.customer_id,
            items=req.items,
            total_amount_cents=total,
        )


class InventoryReservationMessage(BaseModel):
    """Body of the SQS message order-api sends to the inventory queue."""
    order_id: str
    customer_id: str
    items: List[OrderItem]
