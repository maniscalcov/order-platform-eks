"""
Data contracts for payment-worker. OrderStatus mirrors the enum in
order-api/app/models.py and inventory-worker/app/models.py - see the note
in inventory-worker about why this is duplicated rather than shared.
"""
from enum import Enum

from pydantic import BaseModel


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    INVENTORY_RESERVED = "INVENTORY_RESERVED"
    INVENTORY_FAILED = "INVENTORY_FAILED"
    PAYMENT_COMPLETED = "PAYMENT_COMPLETED"
    PAYMENT_FAILED = "PAYMENT_FAILED"


class PaymentRequestMessage(BaseModel):
    """Body of the message consumed from the payment queue."""
    order_id: str
    customer_id: str
    amount_cents: int
