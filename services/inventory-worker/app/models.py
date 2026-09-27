"""
Data contracts for inventory-worker.

OrderItem and InventoryReservationMessage intentionally mirror the shapes
defined in order-api/app/models.py. Each service is an independently
deployable unit with no shared import between them, so the contract is
duplicated rather than shared via a library - a normal trade-off in a small
microservices setup. If this grew past three services, pulling the shared
shapes into a small internal package (or a schema registry) would be the
next step.
"""
from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    INVENTORY_RESERVED = "INVENTORY_RESERVED"
    INVENTORY_FAILED = "INVENTORY_FAILED"
    PAYMENT_COMPLETED = "PAYMENT_COMPLETED"
    PAYMENT_FAILED = "PAYMENT_FAILED"


class OrderItem(BaseModel):
    sku: str
    quantity: int = Field(gt=0)
    unit_price_cents: int = Field(gt=0)


class InventoryReservationMessage(BaseModel):
    """Body of the message consumed from the inventory queue."""
    order_id: str
    customer_id: str
    items: List[OrderItem]


class PaymentRequestMessage(BaseModel):
    """Body of the message published to the payment queue on success."""
    order_id: str
    customer_id: str
    amount_cents: int
