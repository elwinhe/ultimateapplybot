"""
tests/unit/services/test_s3_client.py

"""
from __future__ import annotations

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

# Import the client and its exceptions for testing
from app.services.s3_client import S3Client, S3UploadError, S3ValidationError, s3_client as global_s3_client
from app.config import settings


@mock_aws
def test_s3_client_initialization_success():
    """
    Tests that the S3Client initializes successfully.
    The actual bucket validation happens on the first call, not during init.
    """
    # This test now simply ensures the client can be instantiated
    # without any immediate errors.
    client = S3Client()
    assert client is not None


@mock_aws
def test_validate_filename_rejects_unsafe_names():
    """
    Tests that the private filename validation method rejects unsafe inputs.
    """
    client = S3Client()
    
    with pytest.raises(ValueError, match="path traversal"):
        client._validate_filename("../secret.txt")
        
    with pytest.raises(ValueError, match="invalid characters"):
        client._validate_filename("file with spaces.eml")

    with pytest.raises(ValueError, match="cannot be empty"):
        client._validate_filename("")


@pytest.mark.asyncio
async def test_upload_eml_file_success():
    """
    Tests that a valid file is successfully uploaded to the mock S3 bucket.
    """
    s3_client = S3Client()
    file_content = b"From: test\nSubject: Hello"
    filename = "test-message-id-123.eml"

    with patch.object(s3_client, '_session') as mock_session:
        mock_aio_client = AsyncMock()
        mock_aio_client.put_object = AsyncMock()
        mock_session.client.return_value.__aenter__.return_value = mock_aio_client
        
        s3_key = await s3_client.upload_eml_file(filename=filename, content=file_content)

        # Assert that the correct key was returned
        assert s3_key == f"emails/{filename}"
        
        # Assert that the underlying client was called with the correct parameters
        mock_aio_client.put_object.assert_awaited_once_with(
            Bucket=settings.S3_BUCKET_NAME,
            Key=f"emails/{filename}",
            Body=file_content,
            ContentType='message/rfc822'
        )


@pytest.mark.asyncio
async def test_upload_eml_file_raises_value_error_for_invalid_filename():
    """
    Tests that uploading with an invalid filename raises a ValueError.
    """
    s3_client = S3Client()
    with pytest.raises(ValueError, match="path traversal"):
        await s3_client.upload_eml_file(filename="../../etc/passwd", content=b"hacked")


@pytest.mark.asyncio
async def test_upload_eml_file_raises_upload_error_on_client_error():
    """
    Tests that S3UploadError is raised if aioboto3's put_object fails.
    """
    s3_client = S3Client()
    with patch.object(s3_client._session, 'client') as mock_client:
        mock_s3_client = AsyncMock()
        mock_s3_guts = mock_s3_client.__aenter__.return_value
        mock_s3_guts.put_object.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied', 'Message': 'Access Denied'}},
            'PutObject'
        )
        mock_client.return_value = mock_s3_client

        with pytest.raises(S3UploadError, match="AccessDenied"):
            await s3_client.upload_eml_file(filename="test.eml", content=b"test")


@pytest.mark.asyncio
async def test_upload_eml_fails_if_bucket_not_found():
    """
    Tests that S3UploadError is raised if the bucket does not exist.
    """
    s3_client = S3Client()
    # Patch the client to simulate a NoSuchBucket error
    with patch.object(s3_client, '_session') as mock_session:
        mock_aio_client = AsyncMock()
        mock_aio_client.put_object.side_effect = ClientError(
            {'Error': {'Code': 'NoSuchBucket', 'Message': 'The specified bucket does not exist'}},
            'PutObject'
        )
        mock_session.client.return_value.__aenter__.return_value = mock_aio_client

        with pytest.raises(S3UploadError, match="NoSuchBucket"):
            await s3_client.upload_eml_file(filename="test.eml", content=b"test")


now = datetime.now(timezone.utc)
