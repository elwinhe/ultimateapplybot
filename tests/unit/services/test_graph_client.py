"""
tests/services/test_graph_client.py

Unit tests for the GraphClient service layer.

No network calls made to the Microsoft Graph API.
"""
from __future__ import annotations

import pytest
import httpx
from typing import List
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from datetime import datetime, timezone

from app.services.graph_client import (
    GraphClient,
    GraphAPIFailedRequest,
    GraphClientAuthenticationError,
)
from app.models.email import Email
from app.auth.graph_auth import GraphAuthError, DelegatedGraphAuthenticator


@pytest.fixture
def mock_graph_email_list_payload() -> dict:
    """Provides a valid mock JSON response for a list of emails from the Graph API."""
    return {
        "value": [
            {
                "id": "AAMkAGE1M2_...",
                "receivedDateTime": "2025-06-24T12:00:00Z",
                "subject": "Project Update",
                "hasAttachments": True,
                "from": {
                    "emailAddress": {
                        "name": "Alice Johnson",
                        "address": "alice@contoso.com"
                    }
                },
                "toRecipients": [{"emailAddress": {"address": "bob@contoso.com"}}],
                "body": {
                    "contentType": "html",
                    "content": "<html><body><p>See attached.</p></body></html>"
                }
            }
        ]
    }

@pytest.fixture
def mock_authenticator():
    mock_auth = MagicMock(spec=DelegatedGraphAuthenticator)
    mock_auth.get_access_token_for_user = AsyncMock(return_value="mock-access-token")
    return mock_auth

@pytest.fixture
def mock_http_client():
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.mark.asyncio
async def test_fetch_messages_success(mock_authenticator, mock_http_client):
    """
    Tests successful fetching and parsing of messages when the API returns a 200 OK.
    """
    # Arrange
    mock_response = AsyncMock()
    mock_response.json = Mock(return_value={"value": [{"id": "1", "subject": "Test", "receivedDateTime": datetime.now(timezone.utc).isoformat(), "body": {"contentType": "text", "content": "..."}, "from": {"emailAddress": {"name": "A", "address": "a@example.com"}}, "toRecipients": [{"emailAddress": {"name": "B", "address": "b@example.com"}}], "ccRecipients": [], "bccRecipients": [], "hasAttachments": False}]})
    mock_response.raise_for_status = Mock(return_value=None)
    mock_http_client.get.return_value = mock_response
    
    with patch('app.services.graph_client.DelegatedGraphAuthenticator', return_value=mock_authenticator):
        client = GraphClient(http_client=mock_http_client)
        
        # Act
        emails = await client.fetch_messages()
        
        # Assert
        assert len(emails) == 1
        assert emails[0].id == "1"
        assert emails[0].subject == "Test"
        mock_http_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_messages_authentication_failure(mock_http_client):
    """
    Tests that GraphClientAuthenticationError is raised if the authenticator fails.
    """
    # Arrange
    mock_auth = MagicMock(spec=DelegatedGraphAuthenticator)
    mock_auth.get_access_token_for_user = AsyncMock(side_effect=GraphAuthError("Invalid credentials"))
    
    with patch('app.services.graph_client.DelegatedGraphAuthenticator', return_value=mock_auth):
        client = GraphClient(http_client=mock_http_client)
        # Act & Assert
        with pytest.raises(GraphClientAuthenticationError):
            await client.fetch_messages()


@pytest.mark.asyncio
async def test_fetch_messages_api_failure(mock_authenticator, mock_http_client):
    """
    Tests that GraphAPIFailedRequest is raised when the Graph API returns an error (e.g., 404).
    """
    # Arrange
    mock_http_client.get.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=MagicMock(status_code=401, text="Unauthorized"))
    
    with patch('app.services.graph_client.DelegatedGraphAuthenticator', return_value=mock_authenticator):
        client = GraphClient(http_client=mock_http_client)
        # Act & Assert
        with pytest.raises(GraphAPIFailedRequest):
            await client.fetch_messages()


@pytest.mark.asyncio
async def test_fetch_eml_content_success(mock_authenticator, mock_http_client):
    """
    Tests successful fetching of .eml content when the API returns a 200 OK.
    """
    # Arrange
    mock_response = AsyncMock()
    mock_response.content = b"From: test@example.com\nSubject: Test\n\nContent"
    mock_response.raise_for_status = Mock(return_value=None)
    mock_http_client.get.return_value = mock_response
    
    with patch('app.services.graph_client.DelegatedGraphAuthenticator', return_value=mock_authenticator):
        client = GraphClient(http_client=mock_http_client)
        
        # Act
        content = await client.fetch_eml_content(message_id="123")
        
        # Assert
        assert content == b"From: test@example.com\nSubject: Test\n\nContent"
        mock_http_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_eml_content_api_failure(mock_authenticator, mock_http_client):
    """
    Tests that GraphAPIFailedRequest is raised for a non-200 response.
    """
    # Arrange
    mock_http_client.get.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=MagicMock(status_code=404, text="Not found"))
    
    with patch('app.services.graph_client.DelegatedGraphAuthenticator', return_value=mock_authenticator):
        client = GraphClient(http_client=mock_http_client)
        # Act & Assert
        with pytest.raises(GraphAPIFailedRequest):
            await client.fetch_eml_content(message_id="1")