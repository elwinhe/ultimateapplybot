"""
tests/tasks/test_email_tasks.py

Unit tests for the core Celery task orchestrator.

This suite tests the main business logic of the application, mocking all
external service dependencies to ensure the task's logic is tested in isolation.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from datetime import datetime, timezone

# Import the functions to be tested
from app.tasks.email_tasks import should_process_email, pull_and_process_emails_logic

# Import types and exceptions for creating mocks and testing error handling
from app.services.graph_client import GraphClientError, GraphClientAuthenticationError, GraphAPIFailedRequest
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

@pytest.mark.asyncio
async def test_pull_and_process_emails_happy_path(mock_email_with_invoice, mock_email_no_match, mock_email_tasks_dependencies):
    """Tests the full, successful workflow of fetching, filtering, and archiving an email."""
    mocks = mock_email_tasks_dependencies
    mock_redis = mocks['redis']
    mock_graph_class = patch('app.tasks.email_tasks.GraphClient').start()
    mock_graph = AsyncMock()
    mock_graph_class.return_value = mock_graph
    mock_graph.fetch_messages.return_value = [mock_email_with_invoice, mock_email_no_match]
    mock_graph.fetch_eml_content.return_value = b"MIME content of the email"
    mock_s3 = mocks['s3']
    mock_s3.upload_eml_file = AsyncMock(return_value="emails/invoice_email_123.eml")
    mock_postgres = mocks['postgres']
    mock_postgres.fetch_one = AsyncMock(return_value=None)
    mock_postgres.execute = AsyncMock()

    await pull_and_process_emails_logic()

    mock_redis.get.assert_called_once_with("email_processor:last_seen_timestamp")
    mock_graph.fetch_messages.assert_awaited_once_with(mailbox="me", since=datetime.fromisoformat(mock_redis.get.return_value))
    mock_graph.fetch_eml_content.assert_awaited_once_with(message_id="invoice_email_123", mailbox="me")
    mock_s3.upload_eml_file.assert_awaited_once()
    mock_postgres.execute.assert_awaited_once()
    mock_redis.setex.assert_called_once()
    patch.stopall()

@pytest.mark.asyncio
async def test_pull_and_process_emails_no_new_emails(mock_email_tasks_dependencies):
    """Tests that the task exits gracefully when no new emails are found."""
    mocks = mock_email_tasks_dependencies
    mock_redis = mocks['redis']
    mock_graph_class = patch('app.tasks.email_tasks.GraphClient').start()
    mock_graph = AsyncMock()
    mock_graph_class.return_value = mock_graph
    mock_graph.fetch_messages.return_value = []
    mock_s3 = mocks['s3']
    mock_s3.upload_eml_file = AsyncMock()
    mock_postgres = mocks['postgres']
    mock_postgres.fetch_one = AsyncMock(return_value=None)
    mock_postgres.execute = AsyncMock()

    await pull_and_process_emails_logic()

    mock_graph.fetch_eml_content.assert_not_awaited()
    mock_s3.upload_eml_file.assert_not_awaited()
    mock_postgres.execute.assert_not_awaited()
    patch.stopall()

@pytest.mark.asyncio
async def test_pull_and_process_emails_handles_service_error_gracefully(mock_email_tasks_dependencies):
    """Tests that the task catches and logs errors from a dependency and does not crash."""
    mocks = mock_email_tasks_dependencies
    mock_redis = mocks['redis']
    mock_graph_class = patch('app.tasks.email_tasks.GraphClient').start()
    mock_graph = AsyncMock()
    mock_graph_class.return_value = mock_graph
    mock_graph.fetch_messages.side_effect = GraphAPIFailedRequest("API connection timed out")
    mock_s3 = mocks['s3']
    mock_s3.upload_eml_file = AsyncMock()
    mock_postgres = mocks['postgres']
    mock_postgres.fetch_one = AsyncMock(return_value=None)
    mock_postgres.execute = AsyncMock()

    await pull_and_process_emails_logic()

    mock_s3.upload_eml_file.assert_not_awaited()
    mock_postgres.execute.assert_not_awaited()
    patch.stopall()
