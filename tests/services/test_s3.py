"""
tests/clients/test_s3.py

Unit tests for the S3Client service.

These tests use the 'moto' library to create a mock AWS environment,
ensuring that no real network calls are made to S3.
"""
from __future__ import annotations

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

# Import the client and its exceptions for testing
from app.clients.s3 import S3Client, S3UploadError, S3ValidationError
from app.config import settings


@mock_aws
def test_s3_client_initialization_success():
    """
    Tests that the S3Client initializes successfully when the bucket exists.
    """
    # 1. Set up the mock AWS environment with the required bucket
    s3_conn = boto3.client("s3", region_name=settings.AWS_REGION)
    s3_conn.create_bucket(Bucket=settings.S3_BUCKET_NAME)

    # 2. Initialization should succeed without raising an error
    try:
        S3Client()
    except S3ValidationError:
        pytest.fail("S3Client initialization failed when it should have succeeded.")


@mock_aws
def test_s3_client_initialization_fails_if_bucket_not_found():
    """
    Tests that S3ValidationError is raised if the configured bucket does not exist.
    """
    # In this test, we do NOT create the bucket in the mock environment.
    with pytest.raises(S3ValidationError, match="Cannot access S3 bucket"):
        S3Client()


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


@mock_aws
def test_upload_eml_file_success():
    """
    Tests that a valid file is successfully uploaded to the mock S3 bucket.
    """
    # 1. Set up mock environment and initialize the client
    s3_conn = boto3.client("s3", region_name=settings.AWS_REGION)
    s3_conn.create_bucket(Bucket=settings.S3_BUCKET_NAME)
    s3_client = S3Client()

    # 2. Prepare test data and call the upload method
    file_content = b"From: test\nSubject: Hello"
    filename = "test-message-id-123.eml"
    s3_key = s3_client.upload_eml_file(filename=filename, content=file_content)

    # 3. Assert the returned key is correct
    assert s3_key == f"emails/{filename}"

    # 4. Verify the object exists in the mock S3 bucket with the correct content
    s3_object = s3_conn.get_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)
    assert s3_object["Body"].read() == file_content
    assert s3_object["ContentType"] == 'message/rfc822'


@mock_aws
def test_upload_eml_file_raises_value_error_for_invalid_filename():
    """
    Tests that uploading with an invalid filename raises a ValueError.
    """
    s3_conn = boto3.client("s3", region_name=settings.AWS_REGION)
    s3_conn.create_bucket(Bucket=settings.S3_BUCKET_NAME)
    s3_client = S3Client()

    with pytest.raises(ValueError, match="path traversal"):
        s3_client.upload_eml_file(filename="../../etc/passwd", content=b"hacked")


@mock_aws
def test_upload_eml_file_raises_upload_error_on_client_error(mocker):
    """
    Tests that S3UploadError is raised if boto3's put_object fails.
    """
    s3_conn = boto3.client("s3", region_name=settings.AWS_REGION)
    s3_conn.create_bucket(Bucket=settings.S3_BUCKET_NAME)
    s3_client = S3Client()

    # 1. Mock the internal _s3_client's method to simulate a failure
    mocker.patch.object(
        s3_client._s3_client,
        'put_object',
        side_effect=ClientError({'Error': {'Code': 'AccessDenied', 'Message': 'Access Denied'}}, 'put_object')
    )

    # 2. Assert that our custom S3UploadError is raised
    with pytest.raises(S3UploadError, match="AccessDenied"):
        s3_client.upload_eml_file(filename="test.eml", content=b"test")
