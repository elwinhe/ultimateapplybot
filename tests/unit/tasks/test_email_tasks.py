"""
tests/tasks/test_email_tasks.py

Unit tests for the core Celery task orchestrator.

This suite tests the main business logic of the application, mocking all
external service dependencies to ensure the task's logic is tested in isolation.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

# Import the functions to be tested
from app.tasks.email_tasks import should_process_email, pull_and_process_emails

# Import types and exceptions for creating mocks and testing error handling
from app.services.graph_client import GraphClientError
from app.models.email import Email, EmailAddress, Body


# Fixtures for Mock Data
@pytest.fixture
def mock_email_with_invoice() -> Email:
    """Returns a mock Email object with 'invoice' in the subject."""
    return Email(
        id="invoice_email_123",
        subject="Your Monthly Invoice",
        received_date_time=datetime(2025, 6, 25, 12, 0, 0, tzinfo=timezone.utc),
        body=Body(contentType="html", content="..."),
        from_address=EmailAddress(name="Billing", address="billing@example.com"),
        to_addresses=[EmailAddress(name="User", address="user@example.com")],
        cc_addresses=[], bcc_addresses=[],
        has_attachments=False,
    )

@pytest.fixture
def mock_email_with_attachment() -> Email:
    """Returns a mock Email object with an attachment flag."""
    return Email(
        id="attachment_email_456",
        subject="Quarterly Report",
        received_date_time=datetime(2025, 6, 25, 11, 0, 0, tzinfo=timezone.utc),
        body=Body(contentType="html", content="..."),
        from_address=EmailAddress(name="Reports", address="reports@example.com"),
        to_addresses=[EmailAddress(name="User", address="user@example.com")],
        cc_addresses=[], bcc_addresses=[],
        has_attachments=True,
    )

@pytest.fixture
def mock_email_no_match() -> Email:
    """Returns a mock Email object that should NOT be processed."""
    return Email(
        id="no_match_email_789",
        subject="Hello World",
        received_date_time=datetime(2025, 6, 25, 10, 0, 0, tzinfo=timezone.utc),
        body=Body(contentType="html", content="..."),
        from_address=EmailAddress(name="Test", address="test@example.com"),
        to_addresses=[EmailAddress(name="User", address="user@example.com")],
        cc_addresses=[], bcc_addresses=[],
        has_attachments=False,
    )


# --- Tests for the Pure Filtering Logic ---

def test_should_process_email_matches_on_invoice(mock_email_with_invoice):
    """Tests that an email with 'invoice' in the subject is selected."""
    assert should_process_email(mock_email_with_invoice) is True

def test_should_process_email_matches_on_attachment(mock_email_with_attachment):
    """Tests that an email with attachments is selected."""
    assert should_process_email(mock_email_with_attachment) is True

def test_should_process_email_rejects_non_matching(mock_email_no_match):
    """Tests that a standard email is correctly ignored."""
    assert should_process_email(mock_email_no_match) is False


# --- Tests for the Main Celery Task Orchestrator ---

@pytest.fixture
def mock_dependencies(mocker):
    """A central fixture to mock all external service dependencies for the Celery task."""
    mocker.patch('app.tasks.email_tasks.settings.TARGET_MAILBOX', 'test-user@example.com')
    mocker.patch('app.tasks.email_tasks.settings.REDIS_LAST_SEEN_EXPIRY', 604800) # 7 days

    mock_redis = mocker.patch('app.tasks.email_tasks.redis_client')
    mock_s3 = mocker.patch('app.tasks.email_tasks.s3_client', new_callable=MagicMock)
    mock_postgres = mocker.patch('app.tasks.email_tasks.postgres_client', new_callable=AsyncMock)

    # Mock the GraphClient class and its instance methods
    mock_graph_instance = AsyncMock()
    mocker.patch('app.tasks.email_tasks.GraphClient', return_value=mock_graph_instance)

    # Mock httpx.AsyncClient since it's used directly in the task's with-block
    mocker.patch('app.tasks.email_tasks.httpx.AsyncClient')

    return {
        "redis": mock_redis,
        "s3": mock_s3,
        "postgres": mock_postgres,
        "graph": mock_graph_instance
    }


@pytest.mark.asyncio
async def test_pull_and_process_emails_happy_path(mock_dependencies, mock_email_with_invoice, mock_email_no_match):
    """Tests the full, successful workflow of fetching, filtering, and archiving an email."""
    # 1. Setup mock return values for the dependencies
    mock_dependencies["redis"].get.return_value = datetime.now(timezone.utc).isoformat()
    mock_dependencies["graph"].fetch_messages.return_value = [mock_email_with_invoice, mock_email_no_match]
    mock_dependencies["graph"].fetch_eml_content.return_value = b"MIME content of the email"
    mock_dependencies["s3"].upload_eml_file.return_value = "emails/invoice_email_123.eml"
    
    # Mock the idempotency check to return None (email not processed yet)
    mock_dependencies["postgres"].fetch_one.return_value = None

    # 2. Run the Celery task
    await pull_and_process_emails()

    # 3. Assert that the correct sequence of calls was made
    mock_dependencies["redis"].get.assert_called_once_with("email_processor:last_seen_timestamp")
    mock_dependencies["graph"].fetch_messages.assert_awaited_once()
    
    # Verify that only the matching email was processed
    mock_dependencies["graph"].fetch_eml_content.assert_awaited_once_with(
        message_id="invoice_email_123", mailbox="test-user@example.com"
    )
    mock_dependencies["s3"].upload_eml_file.assert_called_once()
    mock_dependencies["postgres"].execute.assert_awaited_once()

    # Verify that the new high-water mark was set in Redis with an expiry
    mock_dependencies["redis"].setex.assert_called_once_with(
        "email_processor:last_seen_timestamp",
        604800, # The expiry from mocked settings
        mock_email_with_invoice.received_date_time.isoformat()
    )

@pytest.mark.asyncio
async def test_pull_and_process_emails_no_new_emails(mock_dependencies):
    """Tests that the task exits gracefully when no new emails are found."""
    mock_dependencies["redis"].get.return_value = None
    mock_dependencies["graph"].fetch_messages.return_value = [] # Simulate no new emails

    await pull_and_process_emails()

    # Assert that no processing methods were called
    mock_dependencies["graph"].fetch_eml_content.assert_not_awaited()
    mock_dependencies["s3"].upload_eml_file.assert_not_called()
    mock_dependencies["postgres"].execute.assert_not_awaited()
    mock_dependencies["redis"].setex.assert_not_called() # Check setex specifically


@pytest.mark.asyncio
async def test_pull_and_process_emails_handles_service_error_gracefully(mock_dependencies):
    """Tests that the task catches and logs errors from a dependency and does not crash."""
    mock_dependencies["redis"].get.return_value = None
    mock_dependencies["graph"].fetch_messages.side_effect = GraphClientError("API connection timed out")

    # The task should catch the custom exception and finish its run without crashing
    await pull_and_process_emails()

    # Verify that no processing occurred after the failure
    mock_dependencies["s3"].upload_eml_file.assert_not_called()
    mock_dependencies["postgres"].execute.assert_not_awaited()
    # The high-water mark should not be updated on failure
    mock_dependencies["redis"].setex.assert_not_called()
