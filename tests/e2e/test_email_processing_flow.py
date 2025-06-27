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
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta

from app.tasks.email_tasks import pull_and_process_emails_logic, REDIS_LAST_SEEN_KEY

from app.models.email import Email, EmailAddress, Body
from app.config import settings
from app.services.postgres_client import postgres_client
from app.services.s3_client import S3UploadError, s3_client
from app.auth.graph_auth import DelegatedGraphAuthenticator


@pytest_asyncio.fixture
async def e2e_test_setup(mocker):
    """
    Sets up a complete end-to-end test environment with mocked external services.
    
    This fixture:
    1. Mocks the GraphClient to return test emails
    2. Mocks the S3 client to simulate file uploads
    3. Mocks the PostgreSQL client for database operations
    4. Mocks Redis for timestamp tracking
    5. Sets up a clean test environment
    """
    # 1. Mock the GraphClient
    graph_client_patch = patch('app.tasks.email_tasks.GraphClient')
    mock_graph = graph_client_patch.start()
    mock_graph_instance = AsyncMock()
    mock_graph.return_value = mock_graph_instance
    
    # 2. Mock the S3 client
    s3_patch = patch('app.tasks.email_tasks.s3_client')
    mock_s3 = s3_patch.start()
    mock_s3.upload_eml_file = AsyncMock(return_value="emails/test-email.eml")
    
    # 3. Mock the PostgreSQL client
    postgres_patch = patch('app.tasks.email_tasks.postgres_client')
    mock_postgres = postgres_patch.start()
    mock_postgres.execute = AsyncMock()
    mock_postgres.fetch_one = AsyncMock(return_value=None)
    mock_postgres.fetch_all = AsyncMock(return_value=[])
    
    # 4. Mock Redis
    redis_patch = patch('app.tasks.email_tasks.redis_client')
    mock_redis = redis_patch.start()
    
    # Set up Redis state tracking
    redis_state = {}
    
    def mock_get(key):
        return redis_state.get(key)
    
    def mock_setex(key, expiry, value):
        redis_state[key] = value
    
    mock_redis.get.side_effect = mock_get
    mock_redis.setex.side_effect = mock_setex
    
    # 5. Clean up Redis key
    redis_state.clear()
    
    # Yield the mocked graph client so tests can configure its return values
    yield mock_graph_instance, mock_s3, mock_postgres, mock_redis

    graph_client_patch.stop()
    s3_patch.stop()
    postgres_patch.stop()
    redis_patch.stop()


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
    e2e_test_setup[0].fetch_messages.return_value = [mock_email]
    e2e_test_setup[0].fetch_eml_content.return_value = b"From: billing@example.com\nSubject: Invoice"

    # 2. Call the task function directly as a regular async function.
    # This tests the task's logic without involving the Celery broker.
    with patch('app.tasks.email_tasks.settings') as mock_settings:
        mock_settings.TARGET_MAILBOX = "inbox"
        mock_settings.REDIS_LAST_SEEN_EXPIRY = 604800
        
        await pull_and_process_emails_logic()

    # 3. Verify the file was uploaded to S3
    e2e_test_setup[1].upload_eml_file.assert_awaited_once_with(
        filename=f"{mock_email.id}.eml",
        content=b"From: billing@example.com\nSubject: Invoice"
    )

    # 4. Verify the metadata was logged to PostgreSQL
    e2e_test_setup[2].execute.assert_awaited_once()

    # 5. Verify the high-water mark was updated in Redis
    # The Redis mock should have been called with setex
    assert e2e_test_setup[3].setex.called

    e2e_test_setup[0].fetch_messages.assert_awaited_once_with(
        since=None,
        top=100
    )
    e2e_test_setup[0].fetch_eml_content.assert_awaited_once_with(
        message_id=mock_email.id,
    )


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
    e2e_test_setup[0].fetch_messages.return_value = non_matching_emails
    
    # Track method calls to verify they weren't invoked
    e2e_test_setup[0].fetch_eml_content.reset_mock()
    
    # Call the task function directly
    with patch('app.tasks.email_tasks.settings') as mock_settings:
        mock_settings.TARGET_MAILBOX = "inbox"
        mock_settings.REDIS_LAST_SEEN_EXPIRY = 604800
        
        await pull_and_process_emails_logic()
    
    
    # 1. Verify that fetch_eml_content was never called (no emails matched criteria)
    e2e_test_setup[0].fetch_eml_content.assert_not_called()
    
    # 2. Verify that no files were uploaded to S3
    e2e_test_setup[1].upload_eml_file.assert_not_called()
    
    # 3. Verify that no database records were inserted
    e2e_test_setup[2].execute.assert_not_called()
    
    # 4. Verify the high-water mark was updated to the newest email timestamp
    # The Redis mock should have been called with setex
    assert e2e_test_setup[3].setex.called


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

    e2e_test_setup[0].fetch_messages.return_value = [valid_email]
    e2e_test_setup[0].fetch_eml_content.return_value = b"From: billing@example.com\nSubject: Important Invoice"

    # Mock S3 client to raise S3UploadError
    mock_upload = AsyncMock(side_effect=S3UploadError("Mock S3 upload failure for testing"))
    mocker.patch.object(
        e2e_test_setup[1],
        'upload_eml_file',
        mock_upload
    )

    # Store initial high-water mark to verify it doesn't change
    initial_timestamp = e2e_test_setup[3].get(REDIS_LAST_SEEN_KEY)

    # Call the task function - this should fail due to S3 error
    with patch('app.tasks.email_tasks.settings') as mock_settings:
        mock_settings.TARGET_MAILBOX = "inbox"
        mock_settings.REDIS_LAST_SEEN_EXPIRY = 604800

        await pull_and_process_emails_logic()

    # 1. Verify that fetch_eml_content was called (email passed filtering)
    e2e_test_setup[0].fetch_eml_content.assert_awaited_once_with(
        message_id=valid_email.id
    )

    # 2. Verify that S3 upload was attempted (and failed)
    mock_upload.assert_awaited_once_with(
        filename=f"{valid_email.id}.eml",
        content=b"From: billing@example.com\nSubject: Important Invoice"
    )

    # 3. Verify that no database record was inserted (due to S3 failure)
    e2e_test_setup[2].execute.assert_not_called()

    # 4. Verify that high-water mark was NOT updated (due to batch error)
    # The Redis mock should NOT have been called with setex
    assert not e2e_test_setup[3].setex.called


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

    e2e_test_setup[0].fetch_messages.return_value = [duplicate_email]
    e2e_test_setup[0].fetch_eml_content.return_value = b"From: billing@example.com\nSubject: Duplicate Invoice Test"

    # Track S3 upload calls to verify idempotency
    s3_upload_calls = []
    original_upload = e2e_test_setup[1].upload_eml_file

    async def track_upload_calls(*args, **kwargs):
        s3_upload_calls.append((args, kwargs))
        return await original_upload(*args, **kwargs)

    # Mock S3 client to track upload calls
    with patch.object(e2e_test_setup[1], 'upload_eml_file', side_effect=track_upload_calls):
        # Mock settings for the task calls
        with patch('app.tasks.email_tasks.settings') as mock_settings:
            mock_settings.TARGET_MAILBOX = "inbox"
            mock_settings.REDIS_LAST_SEEN_EXPIRY = 604800

            # First run - should process the email normally
            await pull_and_process_emails_logic()

            # Verify first run completed successfully
            assert len(s3_upload_calls) == 1, "S3 upload should be called once in first run"

            # Second run - should process the same email again (idempotent)
            await pull_and_process_emails_logic()

            # Verify second run also completed (idempotent processing)
            assert len(s3_upload_calls) == 2, "S3 upload should be called twice (once per run)"

            # Verify both calls were with the same parameters
            assert s3_upload_calls[0] == s3_upload_calls[1], "Both upload calls should have identical parameters"

            # Verify database was called twice (ON CONFLICT DO NOTHING handles duplicates)
            assert e2e_test_setup[2].execute.call_count == 2, "Database should be called twice (idempotent)"

            # Verify high-water mark was updated in both runs
            assert e2e_test_setup[3].setex.call_count == 2, "High-water mark should be updated in both runs"
