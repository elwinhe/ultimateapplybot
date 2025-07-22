"""
app/tasks/url_extraction_tasks.py

Defines a Celery task for extracting URLs from all emails stored in S3.
"""
from __future__ import annotations

import logging
import email
from email.message import Message
from typing import List, Optional

from bs4 import BeautifulSoup
from urlextract import URLExtract

from app.celery_app import celery
from app.services.s3_client import s3_client
from app.services.postgres_client import postgres_client
from app.tasks.decorators import manage_postgres_connection

logger = logging.getLogger(__name__)

def _get_html_part(msg: Message) -> Optional[str]:
    """Extracts the HTML content from an email message."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                return part.get_payload(decode=True).decode(
                    part.get_content_charset("utf-8"), errors="ignore"
                )
    elif msg.get_content_type() == "text/html":
        return msg.get_payload(decode=True).decode(
            msg.get_content_charset("utf-8"), errors="ignore"
        )
    return None

def _extract_urls_from_eml(eml_content: bytes) -> List[str]:
    """
    Parses .eml content and extracts all unique URLs from its HTML body,
    including both hyperlinks and plain text URLs.
    """
    try:
        msg = email.message_from_bytes(eml_content)
        html_content = _get_html_part(msg)

        if not html_content:
            return []

        soup = BeautifulSoup(html_content, "html.parser")
        
        # 1. Extract URLs from hyperlink hrefs
        href_urls = {a['href'] for a in soup.find_all('a', href=True)}
        
        # 2. Extract URLs from the plain text
        text = soup.get_text()
        extractor = URLExtract()
        text_urls = set(extractor.find_urls(text))
        
        # 3. Combine, filter, and sort
        all_urls = href_urls.union(text_urls)
        
        # Optional: Filter out non-http links if desired
        http_urls = {url for url in all_urls if url.startswith(('http://', 'https://'))}
        
        return sorted(list(http_urls))
        
    except Exception as e:
        logger.error(f"Failed to parse .eml file: {e}", exc_info=True)
        return []

@celery.task(name="extract-urls-from-s3")
def extract_urls_from_s3_emails(results):
    """
    A Celery task that finds unprocessed emails in the database,
    downloads them from S3, parses them, logs any extracted URLs,
    and marks them as processed.
    """
    logger.info("Starting URL extraction task from unprocessed emails.")
    
    # This task now runs synchronously inside the Celery worker,
    # so we need to manage the async event loop.
    import asyncio
    asyncio.run(extract_urls_logic())

@manage_postgres_connection
async def extract_urls_logic():
    """
    The core async logic for the URL extraction task.
    """
    try:
        unprocessed_emails = await postgres_client.fetch_all(
            "SELECT message_id, s3_key FROM archived_emails WHERE urls_extracted_at IS NULL"
        )
        
        if not unprocessed_emails:
            logger.info("No new emails to process for URL extraction.")
            return
            
        logger.info(f"Found {len(unprocessed_emails)} unprocessed emails.")
        total_urls_found = 0

        for email_record in unprocessed_emails:
            message_id = email_record["message_id"]
            s3_key = email_record["s3_key"]
            try:
                eml_content = await s3_client.download_eml_file(s3_key)
                urls = _extract_urls_from_eml(eml_content)
                
                if urls:
                    logger.info(f"Found {len(urls)} URLs in {s3_key}:")
                    for url in urls:
                        logger.info(f"  - Extracted URL: {url}")
                    total_urls_found += len(urls)
                
                # Mark this email as processed
                await postgres_client.execute(
                    "UPDATE archived_emails SET urls_extracted_at = NOW() WHERE message_id = $1",
                    message_id,
                )
                logger.info(f"Successfully processed and marked '{message_id}' as complete.")

            except Exception as e:
                logger.error(f"Failed to process file {s3_key} (message_id: {message_id}): {e}", exc_info=True)
                continue
                
        logger.info(f"URL extraction task finished. Found a total of {total_urls_found} URLs in {len(unprocessed_emails)} emails.")
        
    except Exception as e:
        logger.error(f"A critical error occurred during the URL extraction task: {e}", exc_info=True) 