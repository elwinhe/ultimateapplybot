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
from celery import chord, group

from app.celery_app import celery
from app.config import settings
from app.models.email import Email
from app.services.graph_client import GraphClient, GraphClientError
from app.services.postgres_client import postgres_client
from app.services.sqs_client import sqs_client
from app.tasks.decorators import manage_postgres_connection
from app.services.email_parser import _extract_urls_from_eml, is_valid_job_url

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
    body_lower = email.body.content.lower() if email.body and email.body.content else ""
    job_keywords = [
        "job alerts", "hiring", "job", "new grad",
        "software engineer", "new graduate",
        "university grad", "university graduate", "entry level", "entry-level"
    ]
    sender_whitelist = [
        "master.elh@gmail.com",
        "elwinhe@proton.me"
    ]

    if any(keyword in subject_lower for keyword in job_keywords):
        return True
    if email.from_address.address in sender_whitelist:
        return True
    if any(keyword in body_lower for keyword in job_keywords):
        return True

    return False

# Asynchronous Core Logic for a Single User 
@manage_postgres_connection
async def process_single_mailbox_logic(user_id: str) -> None:
    """
    Contains the core async logic for fetching and processing emails for one user.
    """
    logger.info("Starting email processing logic for user: %s", user_id)
    redis_key = f"email_processor:last_seen_timestamp:{user_id}"

    # 1. Try to get timestamp from Redis
    last_seen_iso = redis_client.get(redis_key)
    
    # 2. If not in Redis, fall back to PostgreSQL
    if not last_seen_iso:
        logger.info("No timestamp in Redis for user %s. Checking PostgreSQL.", user_id)
        db_record = await postgres_client.fetch_one(
            "SELECT last_seen_timestamp FROM auth_tokens WHERE user_id = $1", user_id
        )
        if db_record and db_record["last_seen_timestamp"]:
            last_seen_dt = db_record["last_seen_timestamp"]
            last_seen_iso = last_seen_dt.isoformat()
            # 3. Warm up the Redis cache
            redis_client.setex(redis_key, settings.REDIS_LAST_SEEN_EXPIRY, last_seen_iso)
            logger.info("Warmed up Redis cache for user %s with timestamp from DB: %s", user_id, last_seen_iso)

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

        # Since emails are sorted DESC by receivedDateTime, the first email is the newest.
        # This will be our high-water mark if any emails in the batch succeed.
        potential_new_timestamp = truly_new_emails[0].received_date_time
        processed_count = 0
        any_email_matched_filter = False
        all_messages_to_send = []
        
        for email in truly_new_emails:
            if not should_process_email(email):
                continue

            any_email_matched_filter = True
            try:
                # 1. Fetch .eml content directly
                eml_content = await graph_client.fetch_eml_content(user_id=user_id, message_id=email.id)
                
                # 2. Extract URLs from the content
                urls = _extract_urls_from_eml(eml_content)
                if urls:
                    valid_urls = [url for url in urls if is_valid_job_url(url)]
                    
                    if valid_urls:
                        logger.info(f"Found {len(valid_urls)} valid job URLs in email {email.id}.")
                        for url in valid_urls:
                            all_messages_to_send.append({
                                "url": url,
                                "subject": email.subject,
                                "user_id": user_id,
                                "received_date_time": email.received_date_time.isoformat(),
                            })
                
                processed_count += 1
                logger.info("Successfully processed email %s for user %s for URL extraction.", email.id, user_id)

            except (GraphClientError, Exception) as e:
                logger.error("Failed to process email %s for user %s: %s", email.id, user_id, e, exc_info=True)
                # Note: We continue to the next email, but don't increment processed_count
                continue
        
        # After processing all emails, send all collected messages in batches
        if all_messages_to_send:
            logger.info(f"Sending a total of {len(all_messages_to_send)} URL messages to SQS in batches.")
            await sqs_client.send_message_batch(all_messages_to_send)
            
        logger.info("Processed %d emails for user %s.", processed_count, user_id)
        
        # We update the timestamp if we made forward progress. This means either:
        # 1. We successfully processed at least one email.
        # 2. We scanned all emails and none of them were candidates for processing (so we can skip them next time).
        should_update_timestamp = (processed_count > 0) or (not any_email_matched_filter)

        if should_update_timestamp:
            newest_timestamp_iso = potential_new_timestamp.isoformat()

            # Write to both Redis and PostgreSQL for durability and speed
            redis_client.setex(redis_key, settings.REDIS_LAST_SEEN_EXPIRY, newest_timestamp_iso)
            await postgres_client.execute(
                "UPDATE auth_tokens SET last_seen_timestamp = $1 WHERE user_id = $2",
                potential_new_timestamp,
                user_id,
            )
            logger.info(
                "Updated last-seen timestamp for user %s to %s in Redis and DB",
                user_id,
                newest_timestamp_iso,
            )
        elif truly_new_emails: # This implies emails were found, but none could be successfully processed.
            logger.warning("Batch for user %s had matching emails, but all failed to process. High-water mark not updated to allow for retry.", user_id)

# Synchronous Celery Worker Task 
@celery.task(name="process-single-mailbox", bind=True, max_retries=3)
def process_single_mailbox(self, user_id: str) -> None:
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
def dispatch_email_processing() -> None:
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
async def dispatch_email_processing_logic() -> None:
    """Async logic for dispatching email processing tasks."""
    users = await postgres_client.fetch_all("SELECT user_id FROM auth_tokens;")
    if not users:
        logger.info("No authenticated users found to process.")
        return

    logger.info("Found %d users. Dispatching tasks.", len(users))
    
    # Create a group of tasks and run them directly. No callback needed.
    user_tasks = group(
        process_single_mailbox.s(user["user_id"]) for user in users
    )
    user_tasks.apply_async()

    logger.info("Successfully dispatched processing group with %d user tasks.", len(users))