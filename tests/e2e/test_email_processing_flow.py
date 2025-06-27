"""
tests/e2e/test_email_processing_flow.py

End-to-end tests for the multi-user email processing workflow.

This suite tests the dispatcher and per-user worker tasks against live
(but containerized) Redis, S3, and PostgreSQL services, while mocking the
external Microsoft Graph API.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
import redis
import boto3
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

# Import the logic functions to be tested
from app.tasks.email_tasks import (
    dispatch_email_processing_logic,
    process_single_mailbox_logic
)

# Import types and services needed for setup and verification
from app.models.email import Email, EmailAddress, Body
from app.config import settings
from app.services.postgres_client import postgres_client
from app.services.s3_client import S3UploadError

# Test Setup Fixtures
@pytest_asyncio.fixture
async def e2e_test_setup(mocker):
    """
    A comprehensive fixture to set up the E2E test environment.
    - Mocks the GraphClient to simulate API responses.
    - Provides live, clean connections to Redis, S3, and Postgres.
    """
    # 1. Mock the GraphClient's methods to return predictable data
    mock_graph_client_instance = AsyncMock()
    mocker.patch('app.tasks.email_tasks.GraphClient', return_value=mock_graph_client_instance)

    # 2. Setup live S3 (moto) environment
    s3_conn = boto3.client(
        "s3", region_name=settings.AWS_REGION, endpoint_url="http://moto:5000",
        aws_access_key_id="testing", aws_secret_access_key="testing"
    )
    try:
        if settings.AWS_REGION != "us-east-1":
            s3_conn.create_bucket(
                Bucket=settings.S3_BUCKET_NAME,
                CreateBucketConfiguration={'LocationConstraint': settings.AWS_REGION}
            )
        else:
            s3_conn.create_bucket(Bucket=settings.S3_BUCKET_NAME)
    except (s3_conn.exceptions.BucketAlreadyExists, s3_conn.exceptions.BucketAlreadyOwnedByYou):
        pass

    # 3. Setup live Postgres environment and clean tables
    await postgres_client.initialize()
    await postgres_client.execute("TRUNCATE TABLE auth_tokens, archived_emails RESTART IDENTITY;")

    # 4. Setup live Redis environment and clean keys
    redis_client = redis.Redis.from_url(settings.REDIS_URL)
    for key in redis_client.scan_iter("email_processor:*"):
        redis_client.delete(key)

    # Yield the mocked graph client so tests can configure its return values
    yield mock_graph_client_instance

    # Teardown
    await postgres_client.close()


# Tests for the Dispatcher Task 
@pytest.mark.asyncio
async def test_dispatcher_schedules_tasks_for_authenticated_users(e2e_test_setup):
    """
    Tests that the dispatcher task correctly fetches users from Postgres
    and dispatches a separate Celery task for each one.
    """
    # Arrange: Add two users with refresh tokens to the database
    await postgres_client.execute("INSERT INTO auth_tokens (user_id, encrypted_refresh_token) VALUES ($1, $2), ($3, $4);",
                                  "user1@example.com", "token1", "user2@example.com", "token2")

    # Mock the Celery .delay() method to track calls
    with patch('app.tasks.email_tasks.process_single_mailbox.delay') as mock_delay:
        # Act: Run the dispatcher logic
        await dispatch_email_processing_logic()

        # Assert: Verify that the dispatcher created two tasks
        assert mock_delay.call_count == 2
        mock_delay.assert_any_call(user_id="user1@example.com")
        mock_delay.assert_any_call(user_id="user2@example.com")


# Tests for the Per-User Worker Task 
@pytest.mark.asyncio
async def test_process_single_mailbox_happy_path(e2e_test_setup):
    """
    Tests the full, successful workflow for a single user's mailbox.
    """
    # Arrange
    user_id = "test-user@example.com"
    now_utc = datetime.now(timezone.utc)
    mock_email = Email(
        id="e2e-test-email-id-001", subject="Your E2E Test Invoice", received_date_time=now_utc,
        body=Body(contentType="html", content="<p>Test</p>"), from_address=EmailAddress(address="b@test.com"),
        to_addresses=[EmailAddress(address="recipient@example.com")], cc_addresses=[], bcc_addresses=[], has_attachments=True
    )
    e2e_test_setup.fetch_messages.return_value = [mock_email]
    e2e_test_setup.fetch_eml_content.return_value = b"MIME content"

    # Act
    await process_single_mailbox_logic(user_id)

    # Assert: Verify S3 upload
    s3_conn = boto3.client("s3", region_name=settings.AWS_REGION, endpoint_url="http://moto:5000",
                           aws_access_key_id="testing", aws_secret_access_key="testing")
    s3_key = f"emails/{mock_email.id}.eml"
    s3_object = s3_conn.get_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)
    assert s3_object["Body"].read() == b"MIME content"

    # Assert: Verify Postgres record
    record = await postgres_client.fetch_one("SELECT * FROM archived_emails WHERE message_id = $1", mock_email.id)
    assert record is not None
    assert record["s3_key"] == s3_key

    # Assert: Verify Redis high-water mark
    redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    redis_key = f"email_processor:last_seen_timestamp:{user_id}"
    new_timestamp = redis_client.get(redis_key)
    assert new_timestamp == now_utc.isoformat()


@pytest.mark.asyncio
async def test_process_single_mailbox_s3_failure_handling(e2e_test_setup, mocker):
    """
    Tests that if S3 upload fails for a user, the high-water mark is not updated.
    """
    # Arrange
    user_id = "failing-user@example.com"
    mock_email = Email(
        id="fail-email-id-002", subject="Invoice that will fail", received_date_time=datetime.now(timezone.utc),
        body=Body(contentType="html", content="..."), from_address=EmailAddress(address="c@test.com"),
        to_addresses=[EmailAddress(address="recipient@example.com")], cc_addresses=[], bcc_addresses=[], has_attachments=True
    )
    e2e_test_setup.fetch_messages.return_value = [mock_email]
    e2e_test_setup.fetch_eml_content.return_value = b"MIME content"
    # Mock the S3 client to raise an error
    mocker.patch('app.tasks.email_tasks.s3_client.upload_eml_file', side_effect=S3UploadError("Mock S3 Failure"))

    # Act
    await process_single_mailbox_logic(user_id)

    # Assert: Verify Redis high-water mark was NOT updated
    redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    redis_key = f"email_processor:last_seen_timestamp:{user_id}"
    assert redis_client.get(redis_key) is None
