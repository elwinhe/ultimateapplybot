"""
app/services/email_parser.py

Provides utility functions for parsing email content, such as extracting URLs.
"""
from __future__ import annotations

import logging
import email
from email.message import Message
import re
from typing import List, Optional

from bs4 import BeautifulSoup
from urlextract import URLExtract

logger = logging.getLogger(__name__)


def is_valid_job_url(url: str) -> bool:
    """
    Performs basic rule-based validation to check if a URL is a likely job application link.
    """
    invalid_keywords = [
        "itunes.apple.com",
        "apps.microsoft.com",
        "play.google.com",
        "products",
        "/help/linkedin/answer",
        "unsubscribe",
        "/in/",
        "/feed/",
        "/alerts?",
        "/search?",
        "simplify.jobs",
    ]
    must_contain_keywords = [
        r"\bjobs?\b",      # Matches job or jobs
        r"\bcareers?\b",   # Matches career or careers
        r"\bworking\b",   # Matches working
        r"\bwork\b",      # Matches work
        r"\bhiring\b",     # Matches hiring
    ]

    url_lower = url.lower()

    if any(keyword in url_lower for keyword in invalid_keywords):
        return False
        
    if any(re.search(keyword, url_lower) for keyword in must_contain_keywords):
        return True

    return False


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
        
        return list(http_urls)
        
    except Exception as e:
        logger.error(f"Failed to parse .eml file: {e}", exc_info=True)
        return [] 