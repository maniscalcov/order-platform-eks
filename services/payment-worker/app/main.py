import logging

from app.config import settings
from app.health import start_health_server
from app.worker import run

logging.basicConfig(level=settings.LOG_LEVEL)

if __name__ == "__main__":
    settings.validate()
    start_health_server(settings.HEALTH_CHECK_PORT)
    run()
