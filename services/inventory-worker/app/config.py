"""
Centralized configuration for inventory-worker, read from environment
variables (populated via ConfigMap/Secret in Kubernetes).
"""
import os


class Settings:
    # AWS
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-2")

    # DynamoDB
    ORDERS_TABLE_NAME: str = os.getenv("ORDERS_TABLE_NAME", "order-platform-orders")
    # NOTE: this table does not exist yet in the Phase 1 Terraform - it only
    # created the orders table. You'll need to add an inventory table
    # (partition key: sku, attribute: quantity_available) plus some seed
    # items before this service can run against a live cluster.
    INVENTORY_TABLE_NAME: str = os.getenv(
        "INVENTORY_TABLE_NAME", "order-platform-inventory"
    )

    # SQS
    INVENTORY_QUEUE_URL: str = os.getenv("INVENTORY_QUEUE_URL", "")
    PAYMENT_QUEUE_URL: str = os.getenv("PAYMENT_QUEUE_URL", "")
    POLL_WAIT_TIME_SECONDS: int = int(os.getenv("POLL_WAIT_TIME_SECONDS", "20"))
    MAX_MESSAGES_PER_POLL: int = int(os.getenv("MAX_MESSAGES_PER_POLL", "5"))

    # Service
    SERVICE_NAME: str = "inventory-worker"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    HEALTH_CHECK_PORT: int = int(os.getenv("HEALTH_CHECK_PORT", "8080"))

    def validate(self) -> None:
        missing = [
            name
            for name in ("INVENTORY_QUEUE_URL", "PAYMENT_QUEUE_URL")
            if not getattr(self, name)
        ]
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}"
            )


settings = Settings()
