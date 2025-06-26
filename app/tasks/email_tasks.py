"""
app/tasks/email_tasks.py

Defines the core Celery background task for fetching, filtering,
and archiving emails.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

import httpx
import redis

from app.auth.graph_auth import DelegatedGraphAuthenticator, GraphAuthError
from app.celery_app import celery
from app.config import settings
from app.models.email import Email
from app.services.graph_client import GraphClient, GraphClientAuthenticationError, GraphAPIFailedRequest
from app.services.s3_client import s3_client, S3UploadError
from app.services.postgres_client import postgres_client, PostgresClientError

logger = logging.getLogger(__name__)

# Redis key for tracking the last processed email timestamp
REDIS_LAST_SEEN_KEY = "email_processor:last_seen_timestamp"
REDIS_LAST_SEEN_EXPIRY = settings.REDIS_LAST_SEEN_EXPIRY

def _get_redis_client():
    """Get a Redis client, connecting only when needed."""
    try:
        client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.ping()
        return client
    except Exception as e:
        logger.error("Failed to connect to Redis: %s", e)
        raise RuntimeError("Failed to connect to Redis") from e

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

async def pull_and_process_emails_logic(
    auth_client: Optional[DelegatedGraphAuthenticator] = None
):
    """
    Pure business logic for email processing, separated from Celery task for testability.
    
    Args:
        auth_client: Optional auth client instance for dependency injection
    """
    try:
        # Get Redis client
        redis_client = _get_redis_client()
        
        # Get the last seen timestamp from Redis
        last_seen_str = redis_client.get(REDIS_LAST_SEEN_KEY)
        last_seen = None
        if last_seen_str:
            last_seen = datetime.fromisoformat(last_seen_str)
            logger.info("Processing emails since: %s", last_seen)
        else:
            logger.info("No previous timestamp found, processing all available emails")

        # Fetch emails from Graph API using shared HTTP client
        async with httpx.AsyncClient() as http_client:
            # Create auth client if not provided
            if auth_client is None:
                auth_client = DelegatedGraphAuthenticator(http_client=http_client)
            
            # Create Graph client
            graph_client = GraphClient(http_client=http_client)
            
            try:
                emails = await graph_client.fetch_messages(since=last_seen)
                logger.info("Fetched %d emails from Graph API", len(emails))
            except (GraphClientAuthenticationError, GraphAPIFailedRequest) as e:
                logger.error("Failed to fetch emails from Graph API: %s", e)
                return

            if not emails:
                logger.info("No new emails found")
                return

            # Process each email
            newest_timestamp = last_seen
            successfully_processed_emails = []
            filtered_out_emails = []
            
            for email in emails:
                try:
                    # Update newest timestamp
                    if newest_timestamp is None or email.received_date_time > newest_timestamp:
                        newest_timestamp = email.received_date_time

                    # Check if email should be processed
                    if not should_process_email(email):
                        logger.debug("Skipping email %s (doesn't match criteria)", email.id)
                        filtered_out_emails.append(email)
                        continue

                    # Check if email was already processed (idempotency)
                    existing_record = await postgres_client.fetch_one(
                        "SELECT message_id FROM archived_emails WHERE message_id = $1",
                        email.id
                    )
                    if existing_record:
                        logger.info("Email %s already processed, skipping", email.id)
                        continue

                    # Download raw .eml content
                    try:
                        eml_content = await graph_client.fetch_eml_content(message_id=email.id)
                        logger.info("Downloaded .eml content for email %s (%d bytes)", email.id, len(eml_content))
                    except GraphAPIFailedRequest as e:
                        logger.error("Failed to download .eml content for email %s: %s", email.id, e)
                        continue

                    # Upload to S3
                    try:
                        s3_key = await s3_client.upload_eml_file(
                            filename=f"{email.id}.eml",
                            content=eml_content
                        )
                        logger.info("Uploaded email %s to S3: %s", email.id, s3_key)
                    except S3UploadError as e:
                        logger.error("Failed to upload email %s to S3: %s", email.id, e)
                        continue

                    # Log metadata to PostgreSQL
                    try:
                        await postgres_client.execute(
                            """
                            INSERT INTO archived_emails 
                            (message_id, subject, received_date_time, from_address, to_addresses, s3_key)
                            VALUES ($1, $2, $3, $4, $5, $6)
                            ON CONFLICT (message_id) DO NOTHING
                            """,
                            email.id,
                            email.subject,
                            email.received_date_time,
                            email.from_address.address,
                            [addr.address for addr in email.to_addresses],
                            s3_key
                        )
                        logger.info("Logged metadata for email %s to PostgreSQL", email.id)
                        
                        # Only mark as successfully processed if all steps completed
                        successfully_processed_emails.append(email)
                        
                    except Exception as e:
                        logger.error("Failed to log metadata for email %s to PostgreSQL: %s", email.id, e)
                        # Continue processing other emails even if DB insert fails

                except Exception as e:
                    logger.error("Unexpected error processing email %s: %s", email.id, e)
                    continue

            # Update the high-water mark in Redis
            if successfully_processed_emails:
                # Find the newest timestamp among successfully processed emails
                newest_successful_timestamp = max(email.received_date_time for email in successfully_processed_emails)
                redis_client.setex(
                    REDIS_LAST_SEEN_KEY,
                    settings.REDIS_LAST_SEEN_EXPIRY,
                    newest_successful_timestamp.isoformat()
                )
                logger.info("Updated high-water mark to: %s", newest_successful_timestamp.isoformat())
            elif filtered_out_emails and newest_timestamp and newest_timestamp != last_seen:
                # If emails were filtered out but no emails were processed, update to the newest timestamp
                # This handles the case where emails were fetched but filtered out
                redis_client.setex(
                    REDIS_LAST_SEEN_KEY,
                    settings.REDIS_LAST_SEEN_EXPIRY,
                    newest_timestamp.isoformat()
                )
                logger.info("Updated high-water mark to: %s (emails filtered out)", newest_timestamp.isoformat())

    except Exception as e:
        logger.error("An unexpected critical error occurred in the email task.", exc_info=True)
        raise

# Celery Task Definition
@celery.task(name="email_tasks.pull_and_process_emails", max_retries=3)
async def pull_and_process_emails(self) -> None:
    """
    Main Celery task that orchestrates the email processing workflow.
    
    This task:
    1. Fetches new emails from Microsoft Graph API
    2. Filters emails based on business criteria
    3. Downloads raw .eml content for matching emails
    4. Uploads .eml files to S3
    5. Logs metadata to PostgreSQL
    6. Updates the high-water mark in Redis
    
    The task is idempotent and handles errors gracefully.
    """
    try:
        await pull_and_process_emails_logic()
    except Exception as e:
        logger.error("Celery task failed, will retry if possible.", exc_info=True)
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (2 ** self.request.retries))
        else:
            logger.error("Max retries exceeded for email processing task")
            raise