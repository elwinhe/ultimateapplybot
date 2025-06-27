"""
tests/unit/tasks/test_email_tasks.py

Unit tests for the multi-user Celery task orchestrator.

This suite tests the dispatcher and per-user worker logic, mocking all
external service dependencies to ensure the task's logic is tested in isolation.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, ANY
from datetime import datetime, timezone

# Import the functions to be tested
from app.tasks.email_tasks import (
    should_process_email, 
    dispatch_email_processing_logic,
    process_single_mailbox_logic
)

# Import types and exceptions for creating mocks and testing error handling
from app.services.graph_client import GraphClientError, GraphClientAuthenticationError, GraphAPIFailedRequest
from app.services.s3_client import S3UploadError
from app.services.postgres_client import PostgresClientError
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


# Tests for the Pure Filtering Logic
def test_should_process_email_matches_on_invoice(mock_email_with_invoice):
    """Tests that an email with 'invoice' in the subject is selected."""
    assert should_process_email(mock_email_with_invoice) is True

def test_should_process_email_matches_on_attachment(mock_email_with_attachment):
    """Tests that an email with attachments is selected."""
    assert should_process_email(mock_email_with_attachment) is True

def test_should_process_email_rejects_non_matching(mock_email_no_match):
    """Tests that a standard email is correctly ignored."""
    assert should_process_email(mock_email_no_match) is False


# Tests for the Dispatcher Logic
@pytest.mark.asyncio
async def test_dispatch_email_processing_logic_success():
    """Tests that the dispatcher fetches users and dispatches tasks."""
    # Mock PostgreSQL to return users
    mock_users = [
        {"user_id": "user1@example.com"},
        {"user_id": "user2@example.com"},
        {"user_id": "user3@example.com"}
    ]
    
    with patch('app.tasks.email_tasks.postgres_client') as mock_postgres:
        mock_postgres.fetch_all = AsyncMock(return_value=mock_users)
        
        # Mock the Celery task
        with patch('app.tasks.email_tasks.process_single_mailbox.delay') as mock_delay:
            await dispatch_email_processing_logic()
            
            # Verify users were fetched
            mock_postgres.fetch_all.assert_awaited_once_with("SELECT user_id FROM auth_tokens;")
            
            # Verify tasks were dispatched
            assert mock_delay.call_count == 3
            mock_delay.assert_any_call(user_id="user1@example.com")
            mock_delay.assert_any_call(user_id="user2@example.com")
            mock_delay.assert_any_call(user_id="user3@example.com")


@pytest.mark.asyncio
async def test_dispatch_email_processing_logic_no_users():
    """Tests that the dispatcher handles empty user list gracefully."""
    with patch('app.tasks.email_tasks.postgres_client') as mock_postgres:
        mock_postgres.fetch_all = AsyncMock(return_value=[])
        
        with patch('app.tasks.email_tasks.process_single_mailbox.delay') as mock_delay:
            await dispatch_email_processing_logic()
            
            mock_postgres.fetch_all.assert_awaited_once_with("SELECT user_id FROM auth_tokens;")
            mock_delay.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_email_processing_logic_database_error():
    """Tests that the dispatcher handles database errors gracefully."""
    with patch('app.tasks.email_tasks.postgres_client') as mock_postgres:
        mock_postgres.fetch_all = AsyncMock(side_effect=PostgresClientError("Database connection failed"))
        
        with patch('app.tasks.email_tasks.process_single_mailbox.delay') as mock_delay:
            with pytest.raises(PostgresClientError):
                await dispatch_email_processing_logic()
            
            mock_delay.assert_not_called()


@pytest.mark.asyncio
async def test_dispatch_email_processing_logic_task_dispatch_error():
    """Tests that the dispatcher continues even if some task dispatches fail."""
    mock_users = [
        {"user_id": "user1@example.com"},
        {"user_id": "user2@example.com"},
        {"user_id": "user3@example.com"}
    ]
    
    with patch('app.tasks.email_tasks.postgres_client') as mock_postgres:
        mock_postgres.fetch_all = AsyncMock(return_value=mock_users)
        
        with patch('app.tasks.email_tasks.process_single_mailbox.delay') as mock_delay:
            # Make the second task dispatch fail
            mock_delay.side_effect = [None, Exception("Task dispatch failed"), None]
            
            await dispatch_email_processing_logic()
            
            # Verify all three attempts were made
            assert mock_delay.call_count == 3


# Tests for the Per-User Worker Logic
@pytest.mark.asyncio
async def test_process_single_mailbox_logic_success(mock_email_with_invoice):
    """Tests successful email processing for a single user."""
    user_id = "test-user@example.com"
    
    # Mock Redis
    with patch('app.tasks.email_tasks.redis_client') as mock_redis:
        mock_redis.get.return_value = None  # No previous timestamp
        
        # Mock GraphClient
        with patch('app.tasks.email_tasks.GraphClient') as mock_graph_class:
            mock_graph = AsyncMock()
            mock_graph_class.return_value = mock_graph
            mock_graph.fetch_messages.return_value = [mock_email_with_invoice]
            mock_graph.fetch_eml_content.return_value = b"MIME content"
            
            # Mock S3
            with patch('app.tasks.email_tasks.s3_client') as mock_s3:
                mock_s3.upload_eml_file = AsyncMock(return_value="emails/invoice_email_123.eml")
                
                # Mock PostgreSQL
                with patch('app.tasks.email_tasks.postgres_client') as mock_postgres:
                    mock_postgres.execute = AsyncMock()
                    
                    await process_single_mailbox_logic(user_id)
                    
                    # Verify GraphClient was called with user_id
                    mock_graph.fetch_messages.assert_awaited_once_with(
                        user_id=user_id, since=None, top=100
                    )
                    mock_graph.fetch_eml_content.assert_awaited_once_with(
                        user_id=user_id, message_id="invoice_email_123"
                    )
                    
                    # Verify S3 upload
                    mock_s3.upload_eml_file.assert_awaited_once_with(
                        filename="invoice_email_123.eml", content=b"MIME content"
                    )
                    
                    # Verify PostgreSQL insert
                    mock_postgres.execute.assert_awaited_once()
                    
                    # Verify Redis timestamp update
                    mock_redis.setex.assert_called_once()


@pytest.mark.asyncio
async def test_process_single_mailbox_logic_no_new_emails():
    """Tests that the worker exits gracefully when no new emails are found."""
    user_id = "test-user@example.com"
    
    with patch('app.tasks.email_tasks.redis_client') as mock_redis:
        mock_redis.get.return_value = None
        
        with patch('app.tasks.email_tasks.GraphClient') as mock_graph_class:
            mock_graph = AsyncMock()
            mock_graph_class.return_value = mock_graph
            mock_graph.fetch_messages.return_value = []
            
            with patch('app.tasks.email_tasks.s3_client.upload_eml_file', new_callable=AsyncMock) as mock_s3_upload:
                with patch('app.tasks.email_tasks.postgres_client.execute', new_callable=AsyncMock) as mock_postgres_execute:
                    await process_single_mailbox_logic(user_id)
                    
                    mock_graph.fetch_eml_content.assert_not_awaited()
                    mock_s3_upload.assert_not_awaited()
                    mock_postgres_execute.assert_not_awaited()
                    mock_redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_process_single_mailbox_logic_with_since_timestamp():
    """Tests that the worker uses the since timestamp from Redis."""
    user_id = "test-user@example.com"
    since_timestamp = "2025-06-25T10:00:00+00:00"
    
    with patch('app.tasks.email_tasks.redis_client') as mock_redis:
        mock_redis.get.return_value = since_timestamp
        
        with patch('app.tasks.email_tasks.GraphClient') as mock_graph_class:
            mock_graph = AsyncMock()
            mock_graph_class.return_value = mock_graph
            mock_graph.fetch_messages.return_value = []
            
            with patch('app.tasks.email_tasks.s3_client.upload_eml_file', new_callable=AsyncMock) as mock_s3_upload:
                with patch('app.tasks.email_tasks.postgres_client.execute', new_callable=AsyncMock) as mock_postgres_execute:
                    await process_single_mailbox_logic(user_id)
                    
                    # Verify the since parameter was parsed and passed
                    mock_graph.fetch_messages.assert_awaited_once_with(
                        user_id=user_id, since=ANY, top=100
                    )


@pytest.mark.asyncio
async def test_process_single_mailbox_logic_filters_emails(mock_email_with_invoice, mock_email_no_match):
    """Tests that the worker filters emails correctly."""
    user_id = "test-user@example.com"
    
    with patch('app.tasks.email_tasks.redis_client') as mock_redis:
        mock_redis.get.return_value = None
        
        with patch('app.tasks.email_tasks.GraphClient') as mock_graph_class:
            mock_graph = AsyncMock()
            mock_graph_class.return_value = mock_graph
            # Return both matching and non-matching emails
            mock_graph.fetch_messages.return_value = [mock_email_with_invoice, mock_email_no_match]
            mock_graph.fetch_eml_content.return_value = b"MIME content"
            
            with patch('app.tasks.email_tasks.s3_client.upload_eml_file', new_callable=AsyncMock) as mock_s3_upload:
                mock_s3_upload.return_value = "emails/invoice_email_123.eml"
                
                with patch('app.tasks.email_tasks.postgres_client.execute', new_callable=AsyncMock) as mock_postgres_execute:
                    await process_single_mailbox_logic(user_id)
                    
                    # Should only process the invoice email, not the no-match email
                    mock_graph.fetch_eml_content.assert_awaited_once_with(
                        user_id=user_id, message_id="invoice_email_123"
                    )
                    mock_s3_upload.assert_awaited_once()
                    mock_postgres_execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_single_mailbox_logic_s3_error_handling(mock_email_with_invoice):
    """Tests that S3 upload errors are handled gracefully."""
    user_id = "test-user@example.com"
    
    with patch('app.tasks.email_tasks.redis_client') as mock_redis:
        mock_redis.get.return_value = None
        
        with patch('app.tasks.email_tasks.GraphClient') as mock_graph_class:
            mock_graph = AsyncMock()
            mock_graph_class.return_value = mock_graph
            mock_graph.fetch_messages.return_value = [mock_email_with_invoice]
            mock_graph.fetch_eml_content.return_value = b"MIME content"
            
            with patch('app.tasks.email_tasks.s3_client.upload_eml_file', new_callable=AsyncMock) as mock_s3_upload:
                mock_s3_upload.side_effect = S3UploadError("S3 upload failed")
                
                with patch('app.tasks.email_tasks.postgres_client.execute', new_callable=AsyncMock) as mock_postgres_execute:
                    await process_single_mailbox_logic(user_id)
                    
                    # Should not update Redis timestamp due to error
                    mock_redis.setex.assert_not_called()
                    
                    # Should not insert into PostgreSQL due to error
                    mock_postgres_execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_single_mailbox_logic_graph_api_error_handling():
    """Tests that Graph API errors are handled gracefully."""
    user_id = "test-user@example.com"
    
    with patch('app.tasks.email_tasks.redis_client') as mock_redis:
        mock_redis.get.return_value = None
        
        with patch('app.tasks.email_tasks.GraphClient') as mock_graph_class:
            mock_graph = AsyncMock()
            mock_graph_class.return_value = mock_graph
            mock_graph.fetch_messages.side_effect = GraphAPIFailedRequest("API error")
            
            with patch('app.tasks.email_tasks.s3_client.upload_eml_file', new_callable=AsyncMock) as mock_s3_upload:
                with patch('app.tasks.email_tasks.postgres_client.execute', new_callable=AsyncMock) as mock_postgres_execute:
                    with pytest.raises(GraphAPIFailedRequest):
                        await process_single_mailbox_logic(user_id)
                    
                    mock_s3_upload.assert_not_awaited()
                    mock_postgres_execute.assert_not_awaited()
                    mock_redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_process_single_mailbox_logic_postgres_error_handling(mock_email_with_invoice):
    """Tests that PostgreSQL errors are handled gracefully."""
    user_id = "test-user@example.com"
    
    with patch('app.tasks.email_tasks.redis_client') as mock_redis:
        mock_redis.get.return_value = None
        
        with patch('app.tasks.email_tasks.GraphClient') as mock_graph_class:
            mock_graph = AsyncMock()
            mock_graph_class.return_value = mock_graph
            mock_graph.fetch_messages.return_value = [mock_email_with_invoice]
            mock_graph.fetch_eml_content.return_value = b"MIME content"
            
            with patch('app.tasks.email_tasks.s3_client') as mock_s3:
                mock_s3.upload_eml_file = AsyncMock(return_value="emails/invoice_email_123.eml")
                
                with patch('app.tasks.email_tasks.postgres_client') as mock_postgres:
                    mock_postgres.execute = AsyncMock(side_effect=PostgresClientError("Database error"))
                    
                    await process_single_mailbox_logic(user_id)
                    
                    # Should not update Redis timestamp due to error
                    mock_redis.setex.assert_not_called()


@pytest.mark.asyncio
async def test_process_single_mailbox_logic_batch_error_handling(mock_email_with_invoice):
    """Tests that batch errors prevent Redis timestamp update."""
    user_id = "test-user@example.com"
    
    with patch('app.tasks.email_tasks.redis_client') as mock_redis:
        mock_redis.get.return_value = None
        
        with patch('app.tasks.email_tasks.GraphClient') as mock_graph_class:
            mock_graph = AsyncMock()
            mock_graph_class.return_value = mock_graph
            mock_graph.fetch_messages.return_value = [mock_email_with_invoice]
            mock_graph.fetch_eml_content.return_value = b"MIME content"
            
            with patch('app.tasks.email_tasks.s3_client') as mock_s3:
                # First call succeeds, second call fails
                mock_s3.upload_eml_file = AsyncMock(side_effect=[S3UploadError("S3 error"), "success"])
                
                with patch('app.tasks.email_tasks.postgres_client') as mock_postgres:
                    mock_postgres.execute = AsyncMock()
                    await process_single_mailbox_logic(user_id)
                    
                    # Should not update Redis timestamp due to batch error
                    mock_redis.setex.assert_not_called()
