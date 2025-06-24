# app/tasks/email_tasks.py
# • Celery tasks for email processing
# • Exposes `process_message`
# • Uses `GraphClient` for fetching messages
# • Uses `upload_email_to_s3` for uploading to S3
# • Uses `logging` for logging
# • Uses `typing` for type hints
"""
from __future__ import annotations

import os
from celery import Celery

BROKER_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery: Celery = Celery("email_tasks", broker=BROKER_URL, backend=BROKER_URL)

@celery.task(name="email.process-message", bind=True, max_retries=3)
def process_message(self, message_id: str) -> str:  # noqa: D401,WPS110
    #Background pipeline: fetch email → upload to S3.
    from app.clients.graph import GraphClient
    from app.clients.s3 import upload_email_to_s3

    import asyncio

    async def _io() -> None:
        async with GraphClient() as client:
            msg = await client.fetch_message(message_id)
        await upload_email_to_s3(msg)

    try:
        asyncio.run(_io())
    except Exception as exc:  # pragma: no cover
        raise self.retry(exc=exc, countdown=2 ** self.request.retries) from exc
    return "ok"
"""