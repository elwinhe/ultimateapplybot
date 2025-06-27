"""
tests/integration/test_s3_upload.py

Integration tests for the S3 upload functionality.
"""

import pytest
from app.services.s3_client import s3_client
from app.config import settings
import boto3

@pytest.mark.asyncio
async def test_s3_upload_works():
    filename = "pytest_integration_test.eml"
    content = b"From: test@example.com\nTo: test@demo.com\nSubject: Pytest S3\n\nThis is a test."

    s3_key = await s3_client.upload_eml_file(filename, content)
    
    assert s3_key.startswith("emails/")
    assert filename in s3_key

    # New verification step:
    # Explicitly check the bucket contents right after upload.
    s3_conn = boto3.client("s3", region_name=settings.AWS_REGION)
    response = s3_conn.list_objects_v2(Bucket=settings.S3_BUCKET_NAME)
    
    print("Bucket contents:", response.get('Contents', []))

    keys = [obj['Key'] for obj in response.get('Contents', [])]
    assert s3_key in keys