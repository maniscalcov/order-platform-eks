"""
order-api: the entry point of the order flow.

POST /orders
    - validates the request
    - computes the order total
    - writes the order to DynamoDB with status=PENDING
    - publishes an InventoryReservationMessage to the inventory queue
    - returns the created order

GET /orders/{order_id}
    - reads current order state from DynamoDB (this is how a client polls
      for status - the workers update this same row asynchronously)

GET /health
    - liveness/readiness target for the Kubernetes probes
"""
import logging

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.config import settings
from app.db import get_order, put_order
from app.models import InventoryReservationMessage, Order, OrderCreateRequest
from app.queue import publish_inventory_reservation

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(settings.SERVICE_NAME)

app = FastAPI(title="order-api", version="1.0.0")


@app.on_event("startup")
def _validate_config() -> None:
    settings.validate()
    logger.info("order-api starting up, region=%s", settings.AWS_REGION)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": settings.SERVICE_NAME}


@app.post("/orders", status_code=201)
def create_order(req: OrderCreateRequest) -> Order:
    order = Order.from_request(req)

    # Write first, publish second: the DynamoDB row is the source of truth,
    # the queue message is just a trigger. If publish fails after a
    # successful write, the order is durably PENDING but never advances -
    # that's a known failure mode worth surfacing via a CloudWatch alarm on
    # "orders stuck in PENDING" rather than something to solve in-line here.
    try:
        put_order(order)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="failed to create order") from exc

    try:
        publish_inventory_reservation(
            InventoryReservationMessage(
                order_id=order.order_id,
                customer_id=order.customer_id,
                items=order.items,
            )
        )
    except Exception:
        logger.error(
            "Order %s was written but failed to publish to inventory queue",
            order.order_id,
        )
        # Don't fail the request here - the order exists and is visible to
        # the client. A reconciliation job would pick this up in a fuller
        # build; noted as a known gap for the project write-up.

    return order


@app.get("/orders/{order_id}")
def read_order(order_id: str) -> dict:
    item = get_order(order_id)
    if item is None:
        raise HTTPException(status_code=404, detail="order not found")
    return item


@app.exception_handler(Exception)
def unhandled_exception_handler(request, exc):
    logger.exception("Unhandled exception on %s", request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})
