"""
Centralized configuration for order-api.

All values are read from environment variables so the same container image
can run locally, in CI, or in EKS without code changes. In Kubernetes these
are populated via a ConfigMap (non-secret values) and, if needed, a Secret.
"""
import os


class Settings:
    # AWS
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-2")

    # DynamoDB
    ORDERS_TABLE_NAME: str = os.getenv("ORDERS_TABLE_NAME", "order-platform-orders")

    # SQS - order-api only ever talks to the inventory queue. It has no
    # knowledge of payment-worker; that hand-off is inventory-worker's job.
    # This keeps each service coupled only to its immediate downstream queue.
    INVENTORY_QUEUE_URL: str = os.getenv("INVENTORY_QUEUE_URL", "")

    # Service
    SERVICE_NAME: str = "order-api"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    def validate(self) -> None:
        missing = [
            name
            for name in ("INVENTORY_QUEUE_URL",)
            if not getattr(self, name)
        ]
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}"
            )


settings = Settings()
