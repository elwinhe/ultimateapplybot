"""
app/tasks/email_tasks.py

Defines the core Celery background task for fetching, filtering,
and archiving emails.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List

import httpx
import redis

from app.celery_app import celery
from app.config import settings
from app.models.email import Email
from app.services.graph_client import GraphClient, GraphClientError
from app.services.s3_client import s3_client, S3UploadError
from app.services.postgres_client import postgres_client, PostgresClientError

logger = logging.getLogger(__name__)

# Redis Client Initialization
# Connect to Redis using the validated URL from settings.
try:
    redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    redis_client.ping()
    logger.info("Successfully connected to Redis at %s", settings.REDIS_URL)
except redis.exceptions.ConnectionError as e:
    logger.critical("Could not connect to Redis. The application cannot function.", exc_info=True)
    raise RuntimeError("Failed to connect to Redis") from e

# Use a timestamp as the high-water mark, as this is supported by the Graph API filter.
REDIS_LAST_SEEN_KEY = "email_processor:last_seen_timestamp"


# Pure Business Logic Function
def should_process_email(email: Email) -> bool:
    """
    Determines if an email should be processed based on filtering criteria.
    This pure function is easily unit-testable.

    Args:
        email: The Pydantic Email model instance.

    Returns:
        True if the email matches the criteria, False otherwise.
    """
    # Case-insensitive check for keywords in the subject
    subject_lower = email.subject.lower()
    if "invoice" in subject_lower or "receipt" in subject_lower:
        return True

    # Check if the email has attachments
    if email.has_attachments:
        return True

    return False


# Celery Task Definition
@celery.task(name="email_tasks.pull_and_process_emails")
async def pull_and_process_emails() -> None:
    """
    The main Celery task that orchestrates the email processing workflow.
    """
    logger.info("Starting 'pull_and_process_emails' task run.")

    try:
        # 1. Get the timestamp high-water mark from Redis
        last_seen_iso = redis_client.get(REDIS_LAST_SEEN_KEY)
        since: datetime | None = datetime.fromisoformat(last_seen_iso) if last_seen_iso else None
        
        if since:
            logger.info("Found last-seen timestamp: %s", last_seen_iso)
        else:
            logger.info("No last-seen timestamp found. Will fetch most recent emails.")

        # Manage client lifecycles correctly within an async context
        async with httpx.AsyncClient(timeout=60.0) as http_client:
            # 2. Instantiate service clients
            graph_client = GraphClient(http_client=http_client)
            # The s3_client and postgres_client are imported singletons.

            # 3. Fetch ONLY new email messages using the timestamp
            new_emails: List[Email] = await graph_client.fetch_messages(
                mailbox=settings.TARGET_MAILBOX,
                top=100,
                since=since,
                select=["id", "subject", "from", "receivedDateTime", "hasAttachments"]
            )

            if not new_emails:
                logger.info("No new emails found since last run.")
                return

            logger.info("Fetched %d new emails. Filtering and processing...", len(new_emails))
            processed_count = 0

            # 4. Filter and process each email
            for email in new_emails:
                if should_process_email(email):
                    logger.info("Processing email ID: %s, Subject: '%s'", email.id, email.subject)

                    eml_content = await graph_client.fetch_eml_content(
                        message_id=email.id, mailbox=settings.TARGET_MAILBOX
                    )

                    filename = f"{email.id}.eml"
                    s3_key = await s3_client.upload_eml_file(filename=filename, content=eml_content)

                    # 7. Log metadata to Postgres.
                    # The ON CONFLICT clause provides idempotency at the database level.
                    insert_query = """
                        INSERT INTO archived_emails (message_id, subject, s3_key, archived_at)
                        VALUES ($1, $2, $3, NOW())
                        ON CONFLICT (message_id) DO NOTHING;
                    """
                    await postgres_client.execute(insert_query, email.id, email.subject, s3_key)
                    processed_count += 1

            logger.info("Finished processing. Archived %d out of %d emails.", processed_count, len(new_emails))

            # 8. Update the high-water mark in Redis
            # The newest email is the first one due to the sorting in fetch_messages
            newest_email_timestamp = new_emails[0].received_date_time
            redis_client.set(REDIS_LAST_SEEN_KEY, newest_email_timestamp.isoformat())
            logger.info("Updated last-seen timestamp to: %s", newest_email_timestamp.isoformat())

    except (GraphClientError, S3UploadError, PostgresClientError) as e:
        logger.error("A managed error occurred during the email processing task: %s", str(e), exc_info=True)
    except Exception as e:
        logger.critical("An unexpected critical error occurred in the email task.", exc_info=True)

    logger.info("Task 'pull_and_process_emails' finished.")