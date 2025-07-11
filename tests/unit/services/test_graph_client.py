"""
tests/unit/services/test_graph_client.py

Unit tests for the GraphClient service layer (multi-user design).
No network calls made to the Microsoft Graph API.
"""
from __future__ import annotations

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from datetime import datetime, timezone

from app.services.graph_client import (
    GraphClient,
    GraphAPIFailedRequest,
    GraphClientAuthenticationError,
    GraphClientError,
)
from app.models.email import Email
from app.auth.graph_auth import GraphAuthError, DelegatedGraphAuthenticator

TEST_USER_ID = "user@example.com"

@pytest.fixture
def mock_authenticator():
    mock_auth = MagicMock(spec=DelegatedGraphAuthenticator)
    mock_auth.get_access_token_for_user = AsyncMock(return_value="mock-access-token")
    return mock_auth

@pytest.fixture
def mock_http_client():
    return AsyncMock(spec=httpx.AsyncClient)

@pytest.mark.asyncio
async def test_fetch_messages_single_page(mock_authenticator, mock_http_client):
    """Returns parsed emails for a valid user from a single page of results."""
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.json.return_value = {
        "value": [
            {
                "id": "1",
                "subject": "Test",
                "receivedDateTime": datetime.now(timezone.utc).isoformat(),
                "body": {"contentType": "text", "content": "..."},
                "from": {"emailAddress": {"name": "A", "address": "a@example.com"}},
                "toRecipients": [{"emailAddress": {"name": "B", "address": "b@example.com"}}],
                "ccRecipients": [],
                "bccRecipients": [],
                "hasAttachments": False,
            }
        ]
    }
    mock_response.raise_for_status.return_value = None
    mock_http_client.get.return_value = mock_response

    with patch('app.services.graph_client.DelegatedGraphAuthenticator', return_value=mock_authenticator):
        client = GraphClient(http_client=mock_http_client)
        emails = await client.fetch_messages(user_id=TEST_USER_ID)
        assert len(emails) == 1
        assert emails[0].id == "1"
        assert emails[0].subject == "Test"
        mock_http_client.get.assert_called_once()

@pytest.mark.asyncio
async def test_fetch_messages_pagination(mock_authenticator, mock_http_client):
    """Handles pagination by following the @odata.nextLink."""
    mock_response_1 = MagicMock(spec=httpx.Response)
    mock_response_1.json.return_value = {
        "value": [
            {
                "id": "page1-msg1",
                "subject": "Test 1",
                "receivedDateTime": datetime.now(timezone.utc).isoformat(),
                "body": {"contentType": "text", "content": "..."},
                "from": {"emailAddress": {"name": "A", "address": "a@example.com"}},
                "toRecipients": [{"emailAddress": {"name": "B", "address": "b@example.com"}}],
                "ccRecipients": [], "bccRecipients": [], "hasAttachments": False,
            }
        ],
        "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/messages?page=2",
    }
    mock_response_1.raise_for_status.return_value = None

    mock_response_2 = MagicMock(spec=httpx.Response)
    mock_response_2.json.return_value = {
        "value": [
            {
                "id": "page2-msg1",
                "subject": "Test 2",
                "receivedDateTime": datetime.now(timezone.utc).isoformat(),
                "body": {"contentType": "text", "content": "..."},
                "from": {"emailAddress": {"name": "A", "address": "a@example.com"}},
                "toRecipients": [{"emailAddress": {"name": "C", "address": "c@example.com"}}],
                "ccRecipients": [], "bccRecipients": [], "hasAttachments": False,
            }
        ]
    }
    mock_response_2.raise_for_status.return_value = None

    mock_http_client.get.side_effect = [mock_response_1, mock_response_2]
    
    with patch('app.services.graph_client.DelegatedGraphAuthenticator', return_value=mock_authenticator):
        client = GraphClient(http_client=mock_http_client)
        emails = await client.fetch_messages(user_id=TEST_USER_ID)
        assert len(emails) == 2
        assert emails[0].id == "page1-msg1"
        assert emails[1].id == "page2-msg1"
        assert mock_http_client.get.call_count == 2
        
        # Verify the second call uses the nextLink URL with no additional params
        mock_http_client.get.assert_any_call(
            "https://graph.microsoft.com/v1.0/me/messages?page=2",
            headers={"Authorization": "Bearer mock-access-token"},
            params=None,
        )

@pytest.mark.asyncio
async def test_fetch_messages_input_validation(mock_http_client):
    with patch('app.services.graph_client.DelegatedGraphAuthenticator'):
        client = GraphClient(http_client=mock_http_client)
        with pytest.raises(GraphClientError):
            await client.fetch_messages(user_id=None)
        with pytest.raises(GraphClientError):
            await client.fetch_messages(user_id="", top=10)
        with pytest.raises(GraphClientError):
            await client.fetch_messages(user_id=TEST_USER_ID, top=0)
        with pytest.raises(GraphClientError):
            await client.fetch_messages(user_id=TEST_USER_ID, top=2000)
        with pytest.raises(GraphClientError):
            await client.fetch_messages(user_id=TEST_USER_ID, since="not-a-datetime")

@pytest.mark.asyncio
async def test_fetch_messages_authentication_failure(mock_http_client):
    mock_auth = MagicMock(spec=DelegatedGraphAuthenticator)
    mock_auth.get_access_token_for_user = AsyncMock(side_effect=GraphAuthError("Invalid credentials"))
    with patch('app.services.graph_client.DelegatedGraphAuthenticator', return_value=mock_auth):
        client = GraphClient(http_client=mock_http_client)
        with pytest.raises(GraphClientAuthenticationError):
            await client.fetch_messages(user_id=TEST_USER_ID)

@pytest.mark.asyncio
async def test_fetch_messages_api_failure(mock_authenticator, mock_http_client):
    mock_http_client.get.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=MagicMock(status_code=401, text="Unauthorized"))
    with patch('app.services.graph_client.DelegatedGraphAuthenticator', return_value=mock_authenticator):
        client = GraphClient(http_client=mock_http_client)
        with pytest.raises(GraphAPIFailedRequest):
            await client.fetch_messages(user_id=TEST_USER_ID)

@pytest.mark.asyncio
async def test_fetch_messages_timeout(mock_authenticator, mock_http_client):
    mock_http_client.get.side_effect = httpx.TimeoutException("timeout")
    with patch('app.services.graph_client.DelegatedGraphAuthenticator', return_value=mock_authenticator):
        client = GraphClient(http_client=mock_http_client)
        with pytest.raises(GraphClientError):
            await client.fetch_messages(user_id=TEST_USER_ID)

@pytest.mark.asyncio
async def test_fetch_messages_unexpected_error(mock_authenticator, mock_http_client):
    mock_http_client.get.side_effect = Exception("boom")
    with patch('app.services.graph_client.DelegatedGraphAuthenticator', return_value=mock_authenticator):
        client = GraphClient(http_client=mock_http_client)
        with pytest.raises(GraphClientError):
            await client.fetch_messages(user_id=TEST_USER_ID)

@pytest.mark.asyncio
async def test_fetch_eml_content_success(mock_authenticator, mock_http_client):
    mock_response = AsyncMock()
    mock_response.content = b"From: test@example.com\nSubject: Test\n\nContent"
    mock_response.raise_for_status = Mock(return_value=None)
    mock_http_client.get.return_value = mock_response
    with patch('app.services.graph_client.DelegatedGraphAuthenticator', return_value=mock_authenticator):
        client = GraphClient(http_client=mock_http_client)
        content = await client.fetch_eml_content(user_id=TEST_USER_ID, message_id="123")
        assert content == b"From: test@example.com\nSubject: Test\n\nContent"
        mock_http_client.get.assert_called_once()

@pytest.mark.asyncio
async def test_fetch_eml_content_input_validation(mock_http_client):
    with patch('app.services.graph_client.DelegatedGraphAuthenticator'):
        client = GraphClient(http_client=mock_http_client)
        with pytest.raises(GraphClientError):
            await client.fetch_eml_content(user_id=None, message_id="1")
        with pytest.raises(GraphClientError):
            await client.fetch_eml_content(user_id=TEST_USER_ID, message_id=None)
        with pytest.raises(GraphClientError):
            await client.fetch_eml_content(user_id="", message_id="1")
        with pytest.raises(GraphClientError):
            await client.fetch_eml_content(user_id=TEST_USER_ID, message_id="")

@pytest.mark.asyncio
async def test_fetch_eml_content_authentication_failure(mock_http_client):
    mock_auth = MagicMock(spec=DelegatedGraphAuthenticator)
    mock_auth.get_access_token_for_user = AsyncMock(side_effect=GraphAuthError("Invalid credentials"))
    with patch('app.services.graph_client.DelegatedGraphAuthenticator', return_value=mock_auth):
        client = GraphClient(http_client=mock_http_client)
        with pytest.raises(GraphClientAuthenticationError):
            await client.fetch_eml_content(user_id=TEST_USER_ID, message_id="1")

@pytest.mark.asyncio
async def test_fetch_eml_content_api_failure(mock_authenticator, mock_http_client):
    mock_http_client.get.side_effect = httpx.HTTPStatusError("error", request=MagicMock(), response=MagicMock(status_code=404, text="Not found"))
    with patch('app.services.graph_client.DelegatedGraphAuthenticator', return_value=mock_authenticator):
        client = GraphClient(http_client=mock_http_client)
        with pytest.raises(GraphAPIFailedRequest):
            await client.fetch_eml_content(user_id=TEST_USER_ID, message_id="1")

@pytest.mark.asyncio
async def test_fetch_eml_content_timeout(mock_authenticator, mock_http_client):
    mock_http_client.get.side_effect = httpx.TimeoutException("timeout")
    with patch('app.services.graph_client.DelegatedGraphAuthenticator', return_value=mock_authenticator):
        client = GraphClient(http_client=mock_http_client)
        with pytest.raises(GraphClientError):
            await client.fetch_eml_content(user_id=TEST_USER_ID, message_id="1")

@pytest.mark.asyncio
async def test_fetch_eml_content_unexpected_error(mock_authenticator, mock_http_client):
    mock_http_client.get.side_effect = Exception("boom")
    with patch('app.services.graph_client.DelegatedGraphAuthenticator', return_value=mock_authenticator):
        client = GraphClient(http_client=mock_http_client)
        with pytest.raises(GraphClientError):
            await client.fetch_eml_content(user_id=TEST_USER_ID, message_id="1")