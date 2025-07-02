"""
tests/integration/test_s3_upload.py

Integration tests for the S3 upload functionality.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
import boto3

from app.config import settings
from app.services.s3_client import s3_client


@pytest_asyncio.fixture(autouse=True)
async def clean_s3_bucket():
    """
    Fixture to ensure the S3 bucket is empty before each test run.
    This is critical for test isolation.
    """

    s3_conn = boto3.client("s3", endpoint_url=settings.S3_ENDPOINT_URL, region_name=settings.AWS_REGION)
    
    response = s3_conn.list_objects_v2(Bucket=settings.S3_BUCKET_NAME)
    if 'Contents' in response:
        keys_to_delete = [{'Key': obj['Key']} for obj in response['Contents']]
        s3_conn.delete_objects(Bucket=settings.S3_BUCKET_NAME, Delete={'Objects': keys_to_delete})

    yield


@pytest.mark.asyncio
async def test_s3_upload_works():
    """
    Tests that a basic EML file can be uploaded and its key is returned.
    """
    filename = "pytest_integration_test.eml"
    content = b"From: test@example.com\nTo: test@demo.com\nSubject: Pytest S3\n\nThis is a test."

    s3_key = await s3_client.upload_eml_file(filename, content)
    
    assert s3_key.startswith("emails/")
    assert filename in s3_key

    s3_conn = boto3.client("s3", endpoint_url=settings.S3_ENDPOINT_URL, region_name=settings.AWS_REGION)
    response = s3_conn.list_objects_v2(Bucket=settings.S3_BUCKET_NAME)
    
    print("Bucket contents:", response.get('Contents', []))

    keys = [obj['Key'] for obj in response.get('Contents', [])]
    assert s3_key in keys