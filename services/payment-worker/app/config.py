"""
Centralized configuration for payment-worker, read from environment
variables (populated via ConfigMap/Secret in Kubernetes).
"""
import os


class Settings:
    # AWS
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-2")

    # DynamoDB - payment-worker only ever reads/updates the orders table.
    # It has no table of its own.
    ORDERS_TABLE_NAME: str = os.getenv("ORDERS_TABLE_NAME", "order-platform-orders")

    # SQS - terminal consumer in the saga, nothing to publish downstream.
    PAYMENT_QUEUE_URL: str = os.getenv("PAYMENT_QUEUE_URL", "")
    POLL_WAIT_TIME_SECONDS: int = int(os.getenv("POLL_WAIT_TIME_SECONDS", "20"))
    MAX_MESSAGES_PER_POLL: int = int(os.getenv("MAX_MESSAGES_PER_POLL", "5"))

    # Simulated payment gateway. Crank PAYMENT_FAILURE_RATE up during chaos
    # testing / load testing to exercise the PAYMENT_FAILED path and
    # whatever alerting gets built around it.
    PAYMENT_FAILURE_RATE: float = float(os.getenv("PAYMENT_FAILURE_RATE", "0.1"))

    # Service
    SERVICE_NAME: str = "payment-worker"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    HEALTH_CHECK_PORT: int = int(os.getenv("HEALTH_CHECK_PORT", "8080"))

    def validate(self) -> None:
        missing = [
            name for name in ("PAYMENT_QUEUE_URL",) if not getattr(self, name)
        ]
        if missing:
            raise RuntimeError(
                f"Missing required environment variables: {', '.join(missing)}"
            )


settings = Settings()
