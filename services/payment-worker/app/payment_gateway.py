"""
Stand-in for a real payment processor (Stripe, etc.) so the project can be
run and load-tested end to end without any real payment integration.
"""
import random
import time

from app.config import settings


def simulate_charge(amount_cents: int) -> bool:
    # Simulate realistic network latency to an external processor - this
    # is also what gives the HPA/KEDA autoscaling something to react to
    # under load, rather than every message resolving instantly.
    time.sleep(random.uniform(0.05, 0.3))
    return random.random() >= settings.PAYMENT_FAILURE_RATE
