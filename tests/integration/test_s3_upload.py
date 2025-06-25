"""
tests/integration/test_s3_upload.py

Integration tests for the S3 upload functionality.
"""

from app.services.s3_client import s3_client

def test_s3_upload_works():
    filename = "pytest_integration_test.eml"
    content = b"From: test@example.com\nTo: test@demo.com\nSubject: Pytest S3\n\nThis is a test."

    s3_key = s3_client.upload_eml_file(filename, content)
    
    assert s3_key.startswith("emails/")
    assert filename in s3_key