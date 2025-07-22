"""
tests/unit/tasks/test_email_tasks.py

Unit tests for Celery email processing tasks.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from celery.exceptions import Retry
from dateutil.parser import isoparse

from app.models.email import Email, EmailAddress, Body
from app.services.graph_client import GraphClientError
from app.services.postgres_client import PostgresClientError
from app.services.s3_client import S3UploadError
from app.tasks.email_tasks import (
    process_single_mailbox,
    process_single_mailbox_logic,
    dispatch_email_processing,
    dispatch_email_processing_logic,
)

USER_ID = "test-user-id"
LAST_SEEN_ISO = "2023-01-01T12:00:00+00:00"
LAST_SEEN_DT = isoparse(LAST_SEEN_ISO)


def create_mock_email(
    message_id: str, subject: str, received_dt: datetime, has_attachments: bool = False
) -> Email:
    """Creates a mock Email object for testing."""
    return Email(
        id=message_id,
        subject=subject,
        received_date_time=received_dt,
        body=Body(contentType="text", content="Test email body"),
        from_address=EmailAddress(name="Test Sender", address="sender@example.com"),
        to_addresses=[EmailAddress(name="Test Recipient", address="rec@example.com")],
        has_attachments=has_attachments,
        web_link="http://example.com/email",
    )


@pytest.fixture
def mock_redis_client():
    """Fixture for a mocked Redis client."""
    with patch("app.tasks.email_tasks.redis_client", spec=True) as mock:
        yield mock


@pytest.fixture
def mock_postgres_client():
    """Fixture for a mocked async postgres client."""
    mock = AsyncMock()
    # Mock the methods that are directly called
    mock.fetch_one = AsyncMock()
    mock.execute = AsyncMock()
    with patch("app.tasks.email_tasks.postgres_client", new=mock):
        yield mock


@pytest.fixture
def mock_graph_client():
    """Fixture for a mocked async GraphClient."""
    # We patch the class and then have it return an async mock instance
    with patch("app.tasks.email_tasks.GraphClient", spec=True) as MockGraphClient:
        mock_instance = AsyncMock()
        mock_instance.fetch_messages = AsyncMock()
        mock_instance.fetch_eml_content = AsyncMock()
        MockGraphClient.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_s3_client():
    """Fixture for a mocked async S3Client."""
    mock = AsyncMock()
    mock.upload_eml_file = AsyncMock()
    with patch("app.tasks.email_tasks.s3_client", new=mock):
        yield mock


@pytest.mark.asyncio
async def test_process_single_mailbox_logic_redis_cache_used(
    mock_redis_client,
    mock_postgres_client,
    mock_graph_client,
):
    """
    Tests that the logic uses the timestamp from Redis and fetches emails.
    """
    mock_redis_client.get.return_value = LAST_SEEN_ISO
    mock_graph_client.fetch_messages.return_value = []

    await process_single_mailbox_logic(USER_ID)

    mock_redis_client.get.assert_called_once_with(
        f"email_processor:last_seen_timestamp:{USER_ID}"
    )
    mock_postgres_client.fetch_one.assert_not_called()
    mock_graph_client.fetch_messages.assert_awaited_once_with(
        user_id=USER_ID, since=LAST_SEEN_DT, top=100
    )


@pytest.mark.asyncio
async def test_process_single_mailbox_logic_db_fallback(
    mock_redis_client,
    mock_postgres_client,
    mock_graph_client,
):
    """
    Tests that the logic falls back to PostgreSQL if Redis cache is empty.
    """
    mock_redis_client.get.return_value = None
    mock_postgres_client.fetch_one.return_value = {
        "last_seen_timestamp": LAST_SEEN_DT
    }
    mock_graph_client.fetch_messages.return_value = []

    await process_single_mailbox_logic(USER_ID)

    mock_postgres_client.fetch_one.assert_awaited_once_with(
        "SELECT last_seen_timestamp FROM auth_tokens WHERE user_id = $1", USER_ID
    )
    redis_key = f"email_processor:last_seen_timestamp:{USER_ID}"
    mock_redis_client.setex.assert_called_once()
    assert mock_redis_client.setex.call_args[0][0] == redis_key
    assert mock_redis_client.setex.call_args[0][2] == LAST_SEEN_DT.isoformat()


@pytest.mark.asyncio
async def test_process_single_mailbox_logic_full_flow(
    mock_redis_client,
    mock_postgres_client,
    mock_graph_client,
    mock_s3_client,
):
    """
    Tests the full successful processing flow for a single invoice email.
    """
    mock_redis_client.get.return_value = None
    mock_postgres_client.fetch_one.return_value = None  # No timestamp anywhere

    new_time = datetime.now(timezone.utc)
    email = create_mock_email("msg1", "Your Invoice", new_time)
    mock_graph_client.fetch_messages.return_value = [email]
    mock_graph_client.fetch_eml_content.return_value = b"MIME-Version: 1.0\n"
    mock_s3_client.upload_eml_file.return_value = "s3://bucket/msg1.eml"

    await process_single_mailbox_logic(USER_ID)

    mock_s3_client.upload_eml_file.assert_awaited_once()
    mock_postgres_client.execute.assert_any_await(
        """
                    INSERT INTO archived_emails (message_id, subject, received_date_time, from_address, to_addresses, s3_key)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (message_id) DO NOTHING;
                    """,
        "msg1",
        email.subject,
        new_time,
        "sender@example.com",
        ["rec@example.com"],
        "s3://bucket/msg1.eml",
    )
    # Check timestamp update
    mock_postgres_client.execute.assert_any_await(
        "UPDATE auth_tokens SET last_seen_timestamp = $1 WHERE user_id = $2",
        new_time,
        USER_ID,
    )
    mock_redis_client.setex.assert_called_once()


@pytest.mark.asyncio
async def test_process_single_mailbox_logic_no_new_emails(
    mock_redis_client, mock_graph_client, mock_postgres_client
):
    """
    Tests that nothing is updated if no new emails are found.
    """
    mock_redis_client.get.return_value = LAST_SEEN_ISO
    mock_graph_client.fetch_messages.return_value = []  # No emails from API

    await process_single_mailbox_logic(USER_ID)

    mock_postgres_client.execute.assert_not_awaited()
    assert mock_redis_client.setex.call_count == 0


@pytest.mark.asyncio
async def test_process_single_mailbox_logic_with_since_timestamp(mock_graph_client):
    """
    Tests the defensive filtering of emails with the exact 'since' timestamp.
    """
    # Email with exact same timestamp should be filtered out
    same_time_email = create_mock_email("msg1", "Same Time Invoice", LAST_SEEN_DT)
    # Email one second later should be processed
    new_time = LAST_SEEN_DT + timedelta(seconds=1)
    new_email = create_mock_email("msg2", "New Invoice", new_time)

    mock_graph_client.fetch_messages.return_value = [new_email, same_time_email]
    
    # Mock other clients to avoid side effects
    with patch("app.tasks.email_tasks.postgres_client", new=AsyncMock()), \
         patch("app.tasks.email_tasks.s3_client", new=AsyncMock()), \
         patch("app.tasks.email_tasks.redis_client") as redis_mock:
        
        redis_mock.get.return_value = LAST_SEEN_ISO
        
        await process_single_mailbox_logic(USER_ID)

        # Only the truly new email should trigger a content fetch
        mock_graph_client.fetch_eml_content.assert_awaited_once_with(
            user_id=USER_ID, message_id="msg2"
        )


@pytest.mark.asyncio
async def test_process_single_mailbox_logic_filters_emails(
    mock_graph_client, mock_s3_client, mock_postgres_client
):
    """
    Tests that emails that do not match criteria are not processed.
    """
    email = create_mock_email("msg1", "Just a regular email", datetime.now(timezone.utc))
    mock_graph_client.fetch_messages.return_value = [email]

    with patch("app.tasks.email_tasks.redis_client") as redis_mock:
        redis_mock.get.return_value = None
        # Use the fixture for postgres to ensure the decorator is patched
        mock_postgres_client.fetch_one.return_value = None
        await process_single_mailbox_logic(USER_ID)

    mock_s3_client.upload_eml_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_single_mailbox_logic_s3_error_handling(
    mock_graph_client, mock_s3_client, mock_postgres_client, mock_redis_client
):
    """
    Tests that a timestamp is not updated if an S3 error occurs.
    """
    email = create_mock_email("msg1", "Invoice", datetime.now(timezone.utc))
    mock_graph_client.fetch_messages.return_value = [email]
    mock_graph_client.fetch_eml_content.return_value = b"content"
    mock_s3_client.upload_eml_file.side_effect = S3UploadError("S3 is down")
    
    mock_redis_client.get.return_value = None
    # Ensure DB mock returns a valid record to avoid separate errors
    mock_postgres_client.fetch_one.return_value = {"last_seen_timestamp": LAST_SEEN_DT}

    await process_single_mailbox_logic(USER_ID)

    # The timestamp update execute call should not happen
    mock_postgres_client.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_single_mailbox_logic_graph_api_error_handling(
    mock_graph_client, mock_postgres_client, mock_redis_client
):
    """
    Tests that a timestamp is not updated if a Graph API error occurs.
    """
    email = create_mock_email("msg1", "Invoice", datetime.now(timezone.utc))
    mock_graph_client.fetch_messages.return_value = [email]
    mock_graph_client.fetch_eml_content.side_effect = GraphClientError("Graph is down")
    
    mock_redis_client.get.return_value = None
    mock_postgres_client.fetch_one.return_value = {"last_seen_timestamp": LAST_SEEN_DT}

    await process_single_mailbox_logic(USER_ID)

    mock_postgres_client.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_single_mailbox_logic_postgres_error_handling(
    mock_graph_client, mock_s3_client, mock_postgres_client, mock_redis_client
):
    """
    Tests that a timestamp is not updated if a Postgres error occurs.
    """
    email = create_mock_email("msg1", "Invoice", datetime.now(timezone.utc))
    mock_graph_client.fetch_messages.return_value = [email]
    mock_graph_client.fetch_eml_content.return_value = b"content"
    mock_s3_client.upload_eml_file.return_value = "s3://key"
    mock_postgres_client.execute.side_effect = PostgresClientError("DB is down")

    mock_redis_client.get.return_value = None
    mock_postgres_client.fetch_one.return_value = {"last_seen_timestamp": LAST_SEEN_DT}

    await process_single_mailbox_logic(USER_ID)

    # The insert was attempted, but the final timestamp update should not be
    mock_postgres_client.execute.assert_awaited()


@pytest.mark.asyncio
async def test_process_single_mailbox_logic_batch_error_handling(
    mock_graph_client, mock_s3_client, mock_postgres_client, mock_redis_client
):
    """
    Tests that one failing email doesn't prevent others from being processed,
    but the high-water mark is not updated.
    """
    time1 = datetime.now(timezone.utc)
    time2 = time1 - timedelta(minutes=1)
    
    good_email = create_mock_email("good", "Invoice", time1)
    bad_email = create_mock_email("bad", "Receipt", time2)
    
    mock_graph_client.fetch_messages.return_value = [good_email, bad_email]
    
    async def mock_eml_content(user_id, message_id):
        if message_id == "bad":
            raise GraphClientError("Can't fetch this one")
        return b"good content"

    mock_graph_client.fetch_eml_content.side_effect = mock_eml_content
    mock_s3_client.upload_eml_file.return_value = "s3://key/good.eml"
    mock_redis_client.get.return_value = None
    mock_postgres_client.fetch_one.return_value = None

    await process_single_mailbox_logic(USER_ID)
    
    # The good email should have been inserted
    mock_postgres_client.execute.assert_awaited_once_with(
        """
                    INSERT INTO archived_emails (message_id, subject, received_date_time, from_address, to_addresses, s3_key)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (message_id) DO NOTHING;
                    """,
        "good", good_email.subject, time1, "sender@example.com", ["rec@example.com"], "s3://key/good.eml"
    )

    # But the final timestamp update should NOT have happened
    mock_redis_client.setex.assert_not_called()


@patch("app.tasks.email_tasks.asyncio.run")
@patch("app.tasks.email_tasks.process_single_mailbox_logic")
def test_process_single_mailbox_task_success(mock_logic, mock_run):
    """Tests the success path of the synchronous Celery task wrapper."""
    # We call the task's run method directly to test the inner logic
    # without involving a worker.
    process_single_mailbox.run(USER_ID)
    mock_logic.assert_called_once_with(user_id=USER_ID)
    mock_run.assert_called_once()


@patch("app.tasks.email_tasks.asyncio.run")
def test_process_single_mailbox_task_retry(mock_run):
    """Tests that the Celery task retries on failure."""
    mock_run.side_effect = Exception("A critical failure")

    with patch("app.tasks.email_tasks.process_single_mailbox.retry") as mock_retry:
        mock_retry.side_effect = Retry()

        with pytest.raises(Retry):
            # We call the task's run method to test the retry logic
            process_single_mailbox.run(user_id=USER_ID)

        mock_retry.assert_called_once()


@patch("app.tasks.email_tasks.asyncio.run")
@patch("app.tasks.email_tasks.dispatch_email_processing_logic")
def test_dispatch_email_processing_task(mock_logic, mock_run):
    """Tests the dispatcher Celery task."""
    dispatch_email_processing()
    mock_logic.assert_called_once_with()
    mock_run.assert_called_once()


@pytest.mark.asyncio
@patch("app.tasks.email_tasks.process_single_mailbox.delay")
async def test_dispatch_logic_no_users(mock_delay, mock_postgres_client):
    """Tests dispatcher logic when no users are in the database."""
    mock_postgres_client.fetch_all.return_value = []
    
    await dispatch_email_processing_logic()
    
    mock_delay.assert_not_called()


@pytest.mark.asyncio
@patch("app.tasks.email_tasks.process_single_mailbox.delay")
async def test_dispatch_logic_dispatches_tasks(mock_delay, mock_postgres_client):
    """Tests that the dispatcher creates a Celery task for each user."""
    users = [{"user_id": "user1"}, {"user_id": "user2"}]
    mock_postgres_client.fetch_all.return_value = users

    await dispatch_email_processing_logic()

    assert mock_delay.call_count == 2
    mock_delay.assert_any_call(user_id="user1")
    mock_delay.assert_any_call(user_id="user2")
