"""
app/services/sqs_client.py

Provides a robust, async client for interacting with Amazon SQS.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

import aioboto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings

logger = logging.getLogger(__name__)


class SQSClientError(Exception):
    """Base exception for SQSClient failures."""
    pass


class SQSMessageSendError(SQSClientError):
    """Raised when sending a message to SQS fails."""
    pass


class SQSClient:
    """A thread-safe, async client for interacting with AWS SQS."""

    def __init__(self, endpoint_url: str | None = None) -> None:
        """Initializes the SQS client."""
        self._endpoint_url = endpoint_url
        self._session = aioboto3.Session()
        self._queue_url = settings.SQS_QUEUE_URL
        
        self._client_kwargs = {
            "region_name": settings.AWS_REGION,
            "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
            "endpoint_url": self._endpoint_url,
        }

    async def send_message(self, message_body: Dict[str, Any]) -> str:
        """
        Sends a message to the configured SQS queue.

        Args:
            message_body: A JSON-serializable dictionary to send as the message body.

        Returns:
            The Message ID of the sent message.

        Raises:
            SQSMessageSendError: If the message fails to send.
        """
        if not self._queue_url:
            raise SQSClientError("SQS_QUEUE_URL is not configured.")
            
        try:
            async with self._session.client("sqs", **self._client_kwargs) as sqs:
                response = await sqs.send_message(
                    QueueUrl=self._queue_url,
                    MessageBody=json.dumps(message_body),
                )
                message_id = response.get("MessageId", "N/A")
                logger.info("Successfully sent message to SQS. Message ID: %s", message_id)
                return message_id
        except (ClientError, BotoCoreError) as e:
            logger.error("Failed to send message to SQS queue '%s': %s", self._queue_url, e, exc_info=True)
            raise SQSMessageSendError(f"Failed to send message to SQS: {e}") from e

    async def send_message_batch(self, messages: list[dict[str, Any]]) -> None:
        """
        Sends a batch of messages to the SQS queue, handling chunking.

        Args:
            messages: A list of JSON-serializable dictionaries to send.
        """
        if not self._queue_url:
            raise SQSClientError("SQS_QUEUE_URL is not configured.")

        async with self._session.client("sqs", **self._client_kwargs) as sqs:
            for i in range(0, len(messages), 10):
                batch = messages[i:i + 10]
                entries = [
                    {'Id': str(j), 'MessageBody': json.dumps(msg)}
                    for j, msg in enumerate(batch)
                ]
                try:
                    await sqs.send_message_batch(
                        QueueUrl=self._queue_url,
                        Entries=entries
                    )
                    logger.info(f"Successfully sent a batch of {len(entries)} messages to SQS.")
                except (ClientError, BotoCoreError) as e:
                    logger.error(f"Failed to send a batch to SQS: {e}", exc_info=True)
                    # Optionally, decide if you want to raise or just log the error
                    # For now, we'll log and continue to not halt the entire process
                    continue


# Singleton instance of the SQS client
sqs_client = SQSClient(endpoint_url=getattr(settings, 'S3_ENDPOINT_URL', None)) 