# app/tasks/email_tasks.py
from __future__ import annotations

import os
from celery import Celery

BROKER_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# THIS VARIABLE **MUST** BE NAMED "celery"  ⬇
celery = Celery(
    "email_tasks",
    broker=BROKER_URL,
    backend=BROKER_URL,
)

@celery.task(name="email.fetch_demo")
def fetch_demo(email_id: str) -> str:
    """Dummy task; replace with real logic."""
    return f"processed-{email_id}"
