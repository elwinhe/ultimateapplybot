"""
tests/e2e/test_email_processing_flow.py

End-to-end tests for the primary email processing workflow.

This test suite runs against the live Docker Compose stack but mocks the
external Microsoft Graph API at the boundary. It verifies that the Celery task,
Redis, S3, and PostgreSQL all work together as expected.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
import redis
import boto3
from unittest.mock import AsyncMock
from datetime import datetime, timezone

# Import the Celery task to be triggered
from app.tasks.email_tasks import pull_and_process_emails, REDIS_LAST_SEEN_KEY

# Import types and services needed for setup and verification
from app.models.email import Email, EmailAddress, Body
from app.config import settings
from app.services.postgres_client import postgres_client

# --- Test Setup Fixture ---

@pytest_asyncio.fixture
async def e2e_test_setup(mocker):
    """
    A comprehensive fixture to set up the E2E test environment.
    - Mocks the GraphClient to simulate API responses.
    - Provides a live, clean connection to the S3 (moto) and Postgres services.
    - Clears the Redis key to ensure a clean state.
    """
    # 1. Mock the GraphClient's methods to return predictable data
    mock_graph_client_instance = AsyncMock()
    mocker.patch('app.tasks.email_tasks.GraphClient', return_value=mock_graph_client_instance)

    # 2. Setup a clean, live Redis environment
    redis_client = redis.Redis.from_url(settings.REDIS_URL)
    redis_client.delete(REDIS_LAST_SEEN_KEY)

    # 3. Setup a clean, live S3 (moto) environment
    s3_conn = boto3.client(
        "s3", 
        region_name=settings.AWS_REGION,
        endpoint_url="http://moto:5000",  # Use moto mock service (internal port)
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )
    try:
        # --- THE FIX ---
        # For any region other than us-east-1, S3 requires a LocationConstraint.
        # This makes the test robust regardless of the configured AWS_REGION.
        if settings.AWS_REGION != "us-east-1":
            s3_conn.create_bucket(
                Bucket=settings.S3_BUCKET_NAME,
                CreateBucketConfiguration={'LocationConstraint': settings.AWS_REGION}
            )
        else:
            s3_conn.create_bucket(Bucket=settings.S3_BUCKET_NAME)

    except s3_conn.exceptions.BucketAlreadyExists:
        pass # It's okay if it already exists from a previous run

    # 4. Setup a clean, live Postgres environment
    await postgres_client.initialize()
    await postgres_client.execute("TRUNCATE TABLE archived_emails RESTART IDENTITY;")

    # Yield the mocked graph client so tests can configure its return values
    yield mock_graph_client_instance

    # Teardown
    await postgres_client.close()


# --- End-to-End Test Case ---

@pytest.mark.asyncio
async def test_full_email_processing_flow(e2e_test_setup):
    """
    Tests the full workflow:
    1. A new email is "fetched" from the mocked Graph API.
    2. The task filters and processes it.
    3. The .eml file is saved to S3.
    4. The metadata is logged to PostgreSQL.
    5. The high-water mark is updated in Redis.
    """
    # --- ARRANGE ---
    
    # 1. Configure the mocked GraphClient to return one email to be processed
    now_utc = datetime.now(timezone.utc)
    mock_email = Email(
        id="e2e-test-email-id-001",
        subject="Your E2E Test Invoice",
        received_date_time=now_utc,
        body=Body(contentType="html", content="<p>Test</p>"),
        from_address=EmailAddress(address="billing@example.com"),
        to_addresses=[EmailAddress(address="recipient@example.com")], cc_addresses=[], bcc_addresses=[],
        has_attachments=False,
    )
    e2e_test_setup.fetch_messages.return_value = [mock_email]
    e2e_test_setup.fetch_eml_content.return_value = b"From: billing@example.com\nSubject: Invoice"

    # --- ACT ---

    # 2. Call the task function directly as a regular async function.
    # This tests the task's logic without involving the Celery broker.
    await pull_and_process_emails()

    # --- ASSERT ---

    # 3. Verify the file was uploaded to S3
    s3_conn = boto3.client(
        "s3", 
        region_name=settings.AWS_REGION,
        endpoint_url="http://moto:5000",  # Use moto mock service
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )
    s3_key = f"emails/{mock_email.id}.eml"
    try:
        s3_object = s3_conn.get_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)
        assert s3_object["Body"].read() == b"From: billing@example.com\nSubject: Invoice"
    except s3_conn.exceptions.NoSuchKey:
        pytest.fail(f"File '{s3_key}' was not found in S3 bucket.")

    # 4. Verify the metadata was logged to PostgreSQL
    record = await postgres_client.fetch_one(
        "SELECT * FROM archived_emails WHERE message_id = $1", mock_email.id
    )
    assert record is not None
    assert record["subject"] == "Your E2E Test Invoice"
    assert record["s3_key"] == s3_key

    # 5. Verify the high-water mark was updated in Redis
    redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    new_timestamp = redis_client.get(REDIS_LAST_SEEN_KEY)
    assert new_timestamp is not None
    assert new_timestamp == now_utc.isoformat()
