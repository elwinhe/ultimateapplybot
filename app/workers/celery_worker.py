from __future__ import annotations

import os
from celery import Celery

# Use localhost for local development, redis hostname for Docker
BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery = Celery(  # celery --A app.workers.celery_worker worker
    "email_tasks",
    broker=BROKER_URL,
    backend=BROKER_URL,
)

@celery.task(name="email.fetch-demo")
def fetch_demo(email_id: str) -> str:  # noqa: D401
    """Dummy task that just echoes the id (replace with real logic)."""
    return f"processed-{email_id}"
