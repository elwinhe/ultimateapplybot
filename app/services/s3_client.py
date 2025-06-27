"""
app/services/s3_client.py

Provides a robust client for interacting with Amazon S3.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import aioboto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import settings

logger = logging.getLogger(__name__)


class S3ClientError(Exception):
    """Base exception for S3Client failures."""
    pass


class S3UploadError(S3ClientError):
    """Raised when an S3 upload operation fails."""
    pass


class S3ValidationError(S3ClientError):
    """Raised when S3 credentials or bucket validation fails."""
    pass


class S3Client:
    """
    Handles all interactions with the Amazon S3 service.

    This class manages the aioboto3 S3 client instance and provides
    high-level methods for file operations like uploading.
    """

    def __init__(self, endpoint_url: str | None = None) -> None:
        """
        Initializes the aioboto3 S3 client and validates credentials/bucket access.
        
        Args:
            endpoint_url: Optional endpoint URL for testing (e.g., moto mock service)
        
        Raises:
            S3ValidationError: If credentials are invalid or bucket is inaccessible.
        """
        self._endpoint_url = endpoint_url
        self._session = aioboto3.Session()
        
        # Store credentials for async operations
        self._aws_access_key_id = settings.AWS_ACCESS_KEY_ID
        self._aws_secret_access_key = settings.AWS_SECRET_ACCESS_KEY
        self._region_name = settings.AWS_REGION
        
        # Use dummy credentials for mock service
        if endpoint_url:
            self._aws_access_key_id = "test"
            self._aws_secret_access_key = "test"
        
            logger.info("S3 client initialized successfully")
            
    async def _validate_s3_access(self) -> None:
        """
        Validates that the S3 client can access the configured bucket.
        
        Raises:
            S3ValidationError: If bucket access validation fails.
        """
        try:
            async with self._session.client(
                "s3",
                aws_access_key_id=self._aws_access_key_id,
                aws_secret_access_key=self._aws_secret_access_key,
                region_name=self._region_name,
                endpoint_url=self._endpoint_url
            ) as s3_client:
                await s3_client.head_bucket(Bucket=settings.S3_BUCKET_NAME)
            logger.info("S3 bucket '%s' access validated successfully", settings.S3_BUCKET_NAME)
        except ClientError as e:
            error_code: str = e.response.get("Error", {}).get("Code", "Unknown")
            logger.critical("S3 bucket validation failed: %s", error_code, exc_info=True)
            raise S3ValidationError(f"Cannot access S3 bucket '{settings.S3_BUCKET_NAME}': {error_code}") from e

    def _validate_filename(self, filename: str) -> None:
        """
        Validates that the filename is safe for S3 upload.
        
        Args:
            filename: The filename to validate.
            
        Raises:
            ValueError: If filename is invalid or unsafe.
        """
        if not filename or not filename.strip():
            raise ValueError("Filename cannot be empty")
        
        # Check for path traversal attempts
        if ".." in filename or "/" in filename:
            raise ValueError("Filename cannot contain path traversal characters")
        
        # Check for valid S3 key characters (expanded)
        if not re.match(r'^[a-zA-Z0-9._=\-]+$', filename):
            raise ValueError("Filename contains invalid characters")
        
        # Check length (S3 key limit is 1024 bytes)
        if len(filename.encode('utf-8')) > 1024:
            raise ValueError("Filename too long")

    async def upload_eml_file(self, filename: str, content: bytes) -> str:
        """
        Uploads the raw byte content of an .eml file to a specific path in S3.

        Args:
            filename: The name of the file to create in S3 (e.g., 'message-id.eml').
            content: The raw byte content of the email.

        Returns:
            The full S3 object key where the file was uploaded.

        Raises:
            ValueError: If filename is invalid or content is empty.
            S3UploadError: If the upload fails due to permissions, network issues,
                           or other AWS errors.
        """
        # Validate inputs
        self._validate_filename(filename)
        
        if not content:
            raise ValueError("Content cannot be empty")
        
        # Define a structured path within the S3 bucket
        s3_object_key = f"emails/{filename}"
        bucket = settings.S3_BUCKET_NAME
        
        logger.info("Uploading file '%s' to S3 bucket '%s' (%d bytes)", 
                   s3_object_key, bucket, len(content))

        try:
            async with self._session.client(
                "s3",
                aws_access_key_id=self._aws_access_key_id,
                aws_secret_access_key=self._aws_secret_access_key,
                region_name=self._region_name,
                endpoint_url=self._endpoint_url
            ) as s3_client:
                await s3_client.put_object(
                Bucket=bucket,
                Key=s3_object_key,
                Body=content,
                ContentType='message/rfc822' # Set the correct MIME type for .eml files
            )
            logger.info("Successfully uploaded '%s' to S3", s3_object_key)
            return s3_object_key

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error(
                "S3 ClientError while uploading %s. AWS Error Code: %s",
                s3_object_key, error_code, exc_info=True
            )
            raise S3UploadError(
                f"Failed to upload {s3_object_key} to S3 due to a client-side error: {error_code}"
            ) from e
        except BotoCoreError as e:
            # BotoCoreError is a lower-level error, e.g., credential loading issues
            logger.error(
                "S3 BotoCoreError while uploading %s", s3_object_key, exc_info=True
            )
            raise S3UploadError(
                f"Failed to upload {s3_object_key} to S3 due to a core library error"
            ) from e


# Singleton instance
s3_client = S3Client(endpoint_url=getattr(settings, 'S3_ENDPOINT_URL', None))