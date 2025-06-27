"""
app/tasks/email_tasks.py

Defines the core Celery background task for fetching, filtering,
and archiving emails.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import List, Optional

import httpx
import redis

# Qualified Internal Imports 
from app.celery_app import celery
from app.config import settings
from app.models.email import Email
from app.services.graph_client import GraphClient, GraphClientError
from app.services.s3_client import s3_client, S3UploadError
# CORRECTED: Import the correct base exception name
from app.services.postgres_client import postgres_client, PostgresClientError

logger = logging.getLogger(__name__)

# Redis Client Initialization 
try:
    redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    redis_client.ping()
    logger.info("Successfully connected to Redis at %s", settings.REDIS_URL)
except redis.exceptions.ConnectionError as e:
    logger.critical("Could not connect to Redis. The application cannot function.", exc_info=True)
    raise RuntimeError("Failed to connect to Redis") from e

REDIS_LAST_SEEN_KEY = "email_processor:last_seen_timestamp"


# Pure Business Logic Function 
def should_process_email(email: Email) -> bool:
    """
    Determines if an email should be processed based on filtering criteria.
    This pure function is easily unit-testable.
    """
    subject_lower = email.subject.lower()
    if "invoice" in subject_lower or "receipt" in subject_lower:
        return True
    if email.has_attachments:
        return True
    return False


# Asynchronous Core Logic 
async def pull_and_process_emails_logic() -> None:
    """
    Contains the core asynchronous business logic for the email processing workflow.
    """
    logger.info("Starting async email processing logic.")
    
    last_seen_iso = redis_client.get(REDIS_LAST_SEEN_KEY)
    since: Optional[datetime] = datetime.fromisoformat(last_seen_iso) if last_seen_iso else None
    if since:
        logger.info("Found last-seen timestamp: %s", last_seen_iso)
    else:
        logger.info("No last-seen timestamp found. Will fetch most recent emails.")

    async with httpx.AsyncClient(timeout=60.0) as http_client:
        graph_client = GraphClient(http_client=http_client)
        
        # The GraphClient will automatically use the correct endpoint (/me or /users/{...})
        # based on the application's configuration.
        new_emails: List[Email] = await graph_client.fetch_messages(
            since=since, top=100
        )

        if not new_emails:
            logger.info("No new emails found since last run.")
            return

        logger.info("Fetched %d new emails. Filtering and processing...", len(new_emails))
        processed_count = 0
        batch_had_errors = False # Flag to track if any email in the batch fails

        for email in new_emails:
            if not should_process_email(email):
                continue

            try:
                logger.info("Processing email ID: %s, Subject: '%s'", email.id, email.subject)
                eml_content = await graph_client.fetch_eml_content(
                    message_id=email.id
                )
                filename = f"{email.id}.eml"
                s3_key = await s3_client.upload_eml_file(filename=filename, content=eml_content)
                insert_query = """
                    INSERT INTO archived_emails (message_id, subject, s3_key, archived_at)
                    VALUES ($1, $2, $3, NOW())
                    ON CONFLICT (message_id) DO NOTHING;
                """
                await postgres_client.execute(insert_query, email.id, email.subject, s3_key)
                processed_count += 1
            # CORRECTED: Catch the correct base exception name
            except (GraphClientError, S3UploadError, PostgresClientError) as e:
                logger.error("Failed to process email %s: %s", email.id, e, exc_info=True)
                batch_had_errors = True # Set the flag on failure
                continue

        logger.info("Finished processing batch. Archived %d out of %d emails.", processed_count, len(new_emails))

        if not batch_had_errors:
            newest_email_timestamp = new_emails[0].received_date_time
            redis_client.setex(
                REDIS_LAST_SEEN_KEY,
                settings.REDIS_LAST_SEEN_EXPIRY,
                newest_email_timestamp.isoformat()
            )
            logger.info("Updated last-seen timestamp to: %s", newest_email_timestamp.isoformat())
        else:
            logger.warning("Batch processing had errors. High-water mark will NOT be updated to ensure retry.")


# Synchronous Celery Task Wrapper 
@celery.task(name="email_tasks.pull_and_process_emails", bind=True, max_retries=3)
def pull_and_process_emails(self) -> None:
    """
    The main Celery task that orchestrates the email processing workflow.
    """
    logger.info("Celery task 'pull_and_process_emails' triggered.")
    try:
        asyncio.run(pull_and_process_emails_logic())
    except Exception as e:
        logger.critical("An unexpected critical error occurred in the email task, will retry.", exc_info=True)
        raise self.retry(countdown=60 * (2 ** self.request.retries), exc=e)
    logger.info("Task 'pull_and_process_emails' finished successfully.")
