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
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone, timedelta

# Import the Celery task to be triggered
from app.tasks.email_tasks import pull_and_process_emails, REDIS_LAST_SEEN_KEY

# Import types and services needed for setup and verification
from app.models.email import Email, EmailAddress, Body
from app.config import settings
from app.services.postgres_client import postgres_client
from app.services.s3_client import S3UploadError, s3_client


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
    await postgres_client.create_tables()
    await postgres_client.execute("TRUNCATE TABLE archived_emails RESTART IDENTITY;")

    # Yield the mocked graph client so tests can configure its return values
    yield mock_graph_client_instance

    # Teardown
    await postgres_client.close()


#  End-to-End Test Case
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

    # 2. Call the task function directly as a regular async function.
    # This tests the task's logic without involving the Celery broker.
    await pull_and_process_emails()

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


@pytest.mark.asyncio
async def test_no_emails_match_filtering_criteria(e2e_test_setup):
    """
    Tests that the system correctly handles emails that don't match filtering criteria:
    1. Emails are fetched but filtered out due to no "invoice"/"receipt" in subject and no attachments.
    2. No processing actions are performed (no S3 upload, no DB insert).
    3. High-water mark is still updated to move past unprocessed emails.
    """
    
    # Configure the mocked GraphClient to return emails that don't match criteria
    now_utc = datetime.now(timezone.utc)
    non_matching_emails = [
        Email(
            id="e2e-test-email-id-002",
            subject="Weekly Newsletter",
            received_date_time=now_utc,
            body=Body(contentType="html", content="<p>Newsletter content</p>"),
            from_address=EmailAddress(address="newsletter@example.com"),
            to_addresses=[EmailAddress(address="recipient@example.com")],
            cc_addresses=[],
            bcc_addresses=[],
            has_attachments=False,
        ),
        Email(
            id="e2e-test-email-id-003", 
            subject="Meeting Reminder",
            received_date_time=now_utc + timedelta(minutes=1),  # Slightly newer
            body=Body(contentType="text", content="Meeting reminder"),
            from_address=EmailAddress(address="calendar@example.com"),
            to_addresses=[EmailAddress(address="recipient@example.com")],
            cc_addresses=[],
            bcc_addresses=[],
            has_attachments=False,
        )
    ]
    
    # Set up mock to return non-matching emails
    e2e_test_setup.fetch_messages.return_value = non_matching_emails
    
    # Track method calls to verify they weren't invoked
    e2e_test_setup.fetch_eml_content.reset_mock()
    
    # Call the task function directly
    await pull_and_process_emails()
    
    
    # 1. Verify that fetch_eml_content was never called (no emails matched criteria)
    e2e_test_setup.fetch_eml_content.assert_not_called()
    
    # 2. Verify that no files were uploaded to S3
    s3_conn = boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        endpoint_url="http://moto:5000",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )
    
    # Check that no S3 objects were created for these emails
    for email in non_matching_emails:
        s3_key = f"emails/{email.id}.eml"
        try:
            s3_conn.get_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)
            pytest.fail(f"Unexpected S3 object found: {s3_key}")
        except s3_conn.exceptions.NoSuchKey:
            # Expected - file should not exist
            pass
    
    # 3. Verify that no database records were inserted
    for email in non_matching_emails:
        record = await postgres_client.fetch_one(
            "SELECT * FROM archived_emails WHERE message_id = $1", email.id
        )
        assert record is None, f"Unexpected database record found for email {email.id}"
    
    # 4. Verify the high-water mark was updated to the newest email timestamp
    # (even though no emails were processed, we should move past them)
    redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    new_timestamp = redis_client.get(REDIS_LAST_SEEN_KEY)
    assert new_timestamp is not None, "High-water mark should be updated even for filtered emails"
    
    # Should be set to the newest email's timestamp (the second email)
    expected_timestamp = non_matching_emails[1].received_date_time.isoformat()
    assert new_timestamp == expected_timestamp, (
        f"High-water mark should be updated to newest email timestamp. "
        f"Expected: {expected_timestamp}, Got: {new_timestamp}"
    )


@pytest.mark.asyncio
async def test_s3_upload_failure_handling(e2e_test_setup, mocker):
    """
    Tests that the system handles S3 upload failures gracefully:
    1. A valid email is fetched and passes filtering criteria.
    2. S3 upload fails with S3UploadError.
    3. System stops processing and does not update state.
    4. High-water mark remains unchanged for safe retry.
    """
    
    # Configure the mocked GraphClient to return a valid email
    now_utc = datetime.now(timezone.utc)
    valid_email = Email(
        id="e2e-test-email-id-004",
        subject="Important Invoice",
        received_date_time=now_utc,
        body=Body(contentType="html", content="<p>Invoice content</p>"),
        from_address=EmailAddress(address="billing@example.com"),
        to_addresses=[EmailAddress(address="recipient@example.com")],
        cc_addresses=[],
        bcc_addresses=[],
        has_attachments=False,
    )
    
    e2e_test_setup.fetch_messages.return_value = [valid_email]
    e2e_test_setup.fetch_eml_content.return_value = b"From: billing@example.com\nSubject: Important Invoice"
    
    # Mock S3 client to raise S3UploadError
    mocker.patch.object(
        s3_client, 
        'upload_eml_file', 
        side_effect=S3UploadError("Mock S3 upload failure for testing")
    )
    
    # Store initial high-water mark to verify it doesn't change
    redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    initial_timestamp = redis_client.get(REDIS_LAST_SEEN_KEY)
        
    # Call the task function - this should fail due to S3 error
    await pull_and_process_emails()
        
    # 1. Verify that fetch_eml_content was called (email passed filtering)
    e2e_test_setup.fetch_eml_content.assert_called_once_with(
        message_id=valid_email.id, 
        mailbox=settings.TARGET_MAILBOX
    )
    
    # 2. Verify that S3 upload was attempted (and failed)
    s3_client.upload_eml_file.assert_called_once_with(
        filename=f"{valid_email.id}.eml",
        content=b"From: billing@example.com\nSubject: Important Invoice"
    )
    
    # 3. Verify that no database record was inserted (due to S3 failure)
    record = await postgres_client.fetch_one(
        "SELECT * FROM archived_emails WHERE message_id = $1", valid_email.id
    )
    assert record is None, f"Database record should not exist for email {valid_email.id} after S3 failure"
    
    # 4. Verify that no S3 object was created (upload failed)
    s3_conn = boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        endpoint_url="http://moto:5000",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )
    
    s3_key = f"emails/{valid_email.id}.eml"
    try:
        s3_conn.get_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)
        pytest.fail(f"Unexpected S3 object found after upload failure: {s3_key}")
    except s3_conn.exceptions.NoSuchKey:
        # Expected - file should not exist due to upload failure
        pass
    
    # 5. Verify that the high-water mark was NOT updated (most critical assertion)
    final_timestamp = redis_client.get(REDIS_LAST_SEEN_KEY)
    assert final_timestamp == initial_timestamp, (
        f"High-water mark should remain unchanged after S3 failure to allow safe retry. "
        f"Initial: {initial_timestamp}, Final: {final_timestamp}"
    )
    
    # 6. Verify that the high-water mark is not set to the failed email's timestamp
    if final_timestamp is not None:
        assert final_timestamp != valid_email.received_date_time.isoformat(), (
            f"High-water mark should not be updated to failed email timestamp. "
            f"Current: {final_timestamp}, Failed email: {valid_email.received_date_time.isoformat()}"
        )


@pytest.mark.asyncio
async def test_idempotency_duplicate_email_processing(e2e_test_setup):
    """
    Tests that the system handles duplicate email processing idempotently:
    1. Same email is processed twice in consecutive runs.
    2. S3 upload and database insert occur only once.
    3. ON CONFLICT DO NOTHING logic prevents duplicate records.
    4. High-water mark advances correctly in both runs.
    """
    # Configure the mocked GraphClient to return the same valid email on both runs
    now_utc = datetime.now(timezone.utc)
    duplicate_email = Email(
        id="e2e-test-email-id-005",
        subject="Duplicate Invoice Test",
        received_date_time=now_utc,
        body=Body(contentType="html", content="<p>Duplicate invoice content</p>"),
        from_address=EmailAddress(address="billing@example.com"),
        to_addresses=[EmailAddress(address="recipient@example.com")],
        cc_addresses=[],
        bcc_addresses=[],
        has_attachments=False,
    )
    
    e2e_test_setup.fetch_messages.return_value = [duplicate_email]
    e2e_test_setup.fetch_eml_content.return_value = b"From: billing@example.com\nSubject: Duplicate Invoice Test"
    
    # Track S3 upload calls to verify idempotency
    s3_upload_calls = []
    original_upload = s3_client.upload_eml_file
    
    def track_upload_calls(*args, **kwargs):
        s3_upload_calls.append((args, kwargs))
        return original_upload(*args, **kwargs)
    
    # Mock S3 client to track upload calls
    with patch.object(s3_client, 'upload_eml_file', side_effect=track_upload_calls):
        # First run - should process the email normally
        await pull_and_process_emails()
        
        # Verify first run completed successfully
        assert len(s3_upload_calls) == 1, "S3 upload should be called once in first run"
        
        # Second run - should skip processing due to idempotency
        await pull_and_process_emails()
    
    # Verify total S3 upload calls across both runs
    assert len(s3_upload_calls) == 1, (
        f"S3 upload should be called exactly once across both runs. "
        f"Actual calls: {len(s3_upload_calls)}"
    )
    
    # Verify the S3 upload was called with correct parameters
    expected_filename = f"{duplicate_email.id}.eml"
    expected_content = b"From: billing@example.com\nSubject: Duplicate Invoice Test"
    assert s3_upload_calls[0][0] == (), (
        f"S3 upload should be called with no positional arguments. "
        f"Actual: {s3_upload_calls[0][0]}"
    )
    assert s3_upload_calls[0][1] == {'filename': expected_filename, 'content': expected_content}, (
        f"S3 upload should be called with correct keyword arguments. "
        f"Expected: {{'filename': '{expected_filename}', 'content': {expected_content}}}, "
        f"Actual: {s3_upload_calls[0][1]}"
    )
    
    # Verify S3 object exists and has correct content
    s3_conn = boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        endpoint_url="http://moto:5000",
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )
    
    s3_key = f"emails/{duplicate_email.id}.eml"
    try:
        s3_object = s3_conn.get_object(Bucket=settings.S3_BUCKET_NAME, Key=s3_key)
        assert s3_object["Body"].read() == expected_content, (
            f"S3 object content should match expected content"
        )
    except s3_conn.exceptions.NoSuchKey:
        pytest.fail(f"S3 object should exist after processing: {s3_key}")
    
    # Verify database contains exactly one record for the email
    records = await postgres_client.fetch_all(
        "SELECT * FROM archived_emails WHERE message_id = $1", duplicate_email.id
    )
    assert len(records) == 1, (
        f"Database should contain exactly one record for email {duplicate_email.id}. "
        f"Actual records: {len(records)}"
    )
    
    # Verify the database record has correct data
    record = records[0]
    assert record["message_id"] == duplicate_email.id
    assert record["subject"] == "Duplicate Invoice Test"
    assert record["s3_key"] == s3_key
    
    # Verify high-water mark was updated correctly after both runs
    redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    final_timestamp = redis_client.get(REDIS_LAST_SEEN_KEY)
    assert final_timestamp is not None, "High-water mark should be set after processing"
    assert final_timestamp == duplicate_email.received_date_time.isoformat(), (
        f"High-water mark should match the processed email timestamp. "
        f"Expected: {duplicate_email.received_date_time.isoformat()}, "
        f"Got: {final_timestamp}"
    )
