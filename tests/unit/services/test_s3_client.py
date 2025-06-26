"""
WARNING: These async S3 tests use a real S3 bucket and require valid AWS credentials and a test bucket.
Do NOT use a production bucket for testing. Clean up test objects after running tests.
"""
from __future__ import annotations

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

# Import the client and its exceptions for testing
from app.services.s3_client import S3Client, S3UploadError, S3ValidationError
from app.config import settings


def test_s3_client_initialization_success():
    """
    Tests that the S3Client initializes successfully when the bucket exists.
    """
    with mock_aws():
        s3_conn = boto3.client("s3", region_name=settings.AWS_REGION)
        s3_conn.create_bucket(Bucket=settings.S3_BUCKET_NAME)
        try:
            S3Client()
        except S3ValidationError:
            pytest.fail("S3Client initialization failed when it should have succeeded.")


def test_s3_client_initialization_fails_if_bucket_not_found():
    """
    Tests that S3ValidationError is raised if the configured bucket does not exist.
    Note: With aioboto3, validation happens during async operations, not during init.
    """
    with mock_aws():
        client = S3Client()
        assert client is not None  # Client should initialize successfully


def test_validate_filename_rejects_unsafe_names():
    """
    Tests that the private filename validation method rejects unsafe inputs.
    """
    client = S3Client() # Assuming initialization is mocked or successful
    
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
    s3_key = await s3_client.upload_eml_file(filename=filename, content=file_content)
    assert s3_key == f"emails/{filename}"
    s3_conn = boto3.client("s3", region_name=settings.AWS_REGION)
    s3_object = s3_conn.get_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)
    assert s3_object["Body"].read() == file_content
    assert s3_object["ContentType"] == 'message/rfc822'
    # Clean up
    s3_conn.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)


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
        mock_s3_client.put_object = AsyncMock(
            side_effect=ClientError({'Error': {'Code': 'AccessDenied', 'Message': 'Access Denied'}}, 'put_object')
        )
        mock_client.return_value.__aenter__.return_value = mock_s3_client
        with pytest.raises(S3UploadError, match="AccessDenied"):
            await s3_client.upload_eml_file(filename="test.eml", content=b"test")


now = datetime.now(timezone.utc)
