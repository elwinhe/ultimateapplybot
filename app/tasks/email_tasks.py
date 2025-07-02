"""
app/tasks/email_tasks.py

Defines Celery tasks for fetching emails from multiple user accounts
using a fan-out pattern.
"""
from __future__ import annotations

import asyncio
import logging
from dateutil.parser import isoparse

import httpx
import redis

from app.celery_app import celery
from app.config import settings
from app.models.email import Email
from app.services.graph_client import GraphClient, GraphClientError
from app.services.s3_client import s3_client, S3UploadError
from app.services.postgres_client import postgres_client, PostgresClientError
from app.tasks.decorators import manage_postgres_connection

logger = logging.getLogger(__name__)

# Redis Client Initialization 
try:
    redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    redis_client.ping()
    logger.info("Successfully connected to Redis at %s", settings.REDIS_URL)
except redis.exceptions.ConnectionError as e:
    logger.critical("Could not connect to Redis. The application cannot function.", exc_info=True)
    raise RuntimeError("Failed to connect to Redis") from e

def should_process_email(email: Email) -> bool:
    """Determines if an email should be processed based on filtering criteria."""
    subject_lower = email.subject.lower()
    if "invoice" in subject_lower or "receipt" in subject_lower:
        return True
    if email.has_attachments:
        return True
    return False

# Asynchronous Core Logic for a Single User 
@manage_postgres_connection
async def process_single_mailbox_logic(user_id: str):
    """
    Contains the core async logic for fetching and processing emails for one user.
    """
    logger.info("Starting email processing logic for user: %s", user_id)
    redis_key = f"email_processor:last_seen_timestamp:{user_id}"
    
    last_seen_iso = redis_client.get(redis_key)
    since = isoparse(last_seen_iso) if last_seen_iso else None

    async with httpx.AsyncClient(timeout=60.0) as http_client:
        graph_client = GraphClient(http_client=http_client)
        new_emails = await graph_client.fetch_messages(user_id=user_id, since=since, top=100)

        # Defensively filter out any emails that the API may have returned with a timestamp
        # equal to our 'since' parameter, which can happen due to timestamp precision issues.
        if since:
            truly_new_emails = [e for e in new_emails if e.received_date_time > since]
        else:
            truly_new_emails = new_emails

        if not truly_new_emails:
            logger.info("No new emails found for user %s after defensive filtering.", user_id)
            return

        batch_had_errors = False
        processed_count = 0
        
        for email in truly_new_emails:
            if not should_process_email(email):
                continue
            
            try:
                eml_content = await graph_client.fetch_eml_content(user_id=user_id, message_id=email.id)
                filename = f"{email.id}.eml"
                s3_key = await s3_client.upload_eml_file(filename=filename, content=eml_content)
                await postgres_client.execute(
                    """
                    INSERT INTO archived_emails (message_id, subject, received_date_time, from_address, to_addresses, s3_key)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (message_id) DO NOTHING;
                    """,
                    email.id,
                    email.subject,
                    email.received_date_time,
                    email.from_address.address if email.from_address else None,
                    [addr.address for addr in email.to_addresses],
                    s3_key
                )
                processed_count += 1
                logger.info("Successfully processed email %s for user %s", email.id, user_id)
            except (GraphClientError, S3UploadError, PostgresClientError) as e:
                logger.error("Failed to process email %s for user %s: %s", email.id, user_id, e, exc_info=True)
                batch_had_errors = True
                continue
        
        logger.info("Processed %d emails for user %s", processed_count, user_id)
        
        # Only update the timestamp if the batch was fully successful.
        if not batch_had_errors:
            newest_timestamp_iso = truly_new_emails[0].received_date_time.isoformat()
            redis_client.setex(redis_key, settings.REDIS_LAST_SEEN_EXPIRY, newest_timestamp_iso)
            logger.info("Updated last-seen timestamp for user %s to %s", user_id, newest_timestamp_iso)
        else:
            logger.warning("Batch for user %s had errors. High-water mark not updated.", user_id)

# Synchronous Celery Worker Task 
@celery.task(name="process-single-mailbox", bind=True, max_retries=3)
def process_single_mailbox(self, user_id: str):
    """
    Synchronous Celery task wrapper that executes the async logic for a single user.
    """
    logger.info("Celery worker task triggered for user: %s", user_id)
    try:
        asyncio.run(process_single_mailbox_logic(user_id=user_id))
    except Exception as e:
        logger.critical("Unexpected critical error processing for user %s: %s", user_id, str(e), exc_info=True)
        raise self.retry(countdown=60 * (2 ** self.request.retries), exc=e)

# Synchronous Celery Dispatcher Task 
@celery.task(name="dispatch-email-processing")
def dispatch_email_processing():
    """
    The main scheduled task. It fetches all authenticated users and dispatches
    a separate worker task for each one.
    """
    logger.info("Dispatcher task running: finding users to process...")
    try:
        asyncio.run(dispatch_email_processing_logic())
    except Exception as e:
        logger.error("Failed to dispatch email processing tasks: %s", str(e), exc_info=True)

@manage_postgres_connection
async def dispatch_email_processing_logic():
    """Async logic for dispatching email processing tasks."""
    users = await postgres_client.fetch_all("SELECT user_id FROM auth_tokens;")
    if not users:
        logger.info("No authenticated users found to process.")
        return

    logger.info("Found %d users. Dispatching tasks...", len(users))
    dispatched_count = 0
    
    for user in users:
        user_id = user["user_id"]
        try:
            logger.info("Dispatching task for user: %s", user_id)
            process_single_mailbox.delay(user_id=user_id)
            dispatched_count += 1
        except Exception as e:
            logger.error("Failed to dispatch task for user %s: %s", user_id, str(e))
            continue
            
    logger.info("Successfully dispatched %d out of %d user tasks", dispatched_count, len(users))