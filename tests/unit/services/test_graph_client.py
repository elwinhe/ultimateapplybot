"""
tests/services/test_graph_client.py

Unit tests for the GraphClient service layer.

No network calls made to the Microsoft Graph API.
"""
from __future__ import annotations

import pytest
import httpx
from typing import List
from unittest.mock import AsyncMock

from app.services.graph_client import (
    GraphClient,
    GraphAPIFailedRequest,
    GraphClientAuthenticationError,
)
from app.models.email import Email
from app.auth.graph_auth import GraphAuthError


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
def mock_authenticator(mocker) -> None:
    """Mocks the delegated_auth_client singleton and its get_access_token_for_user method."""
    mock_auth = AsyncMock()
    mock_auth.get_access_token_for_user = AsyncMock(return_value="mock-access-token")
    return mocker.patch(
        'app.services.graph_client.delegated_auth_client',
        mock_auth
    )


@pytest.mark.asyncio
async def test_fetch_messages_success(mock_authenticator, mock_graph_email_list_payload):
    """
    Tests successful fetching and parsing of messages when the API returns a 200 OK.
    """
    # 1. Define a mock transport that returns a successful response
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json=mock_graph_email_list_payload)
    )

    # 2. Instantiate the client with the mock transport
    async with httpx.AsyncClient(transport=transport) as http_client:
        graph_client = GraphClient(http_client=http_client)
        
        # 3. Call the method and assert the results
        emails: List[Email] = await graph_client.fetch_messages(mailbox="me")
        assert len(emails) == 1
        assert isinstance(emails[0], Email)
        assert emails[0].subject == "Project Update"
        mock_authenticator.get_access_token_for_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_messages_authentication_failure(mocker):
    """
    Tests that GraphClientAuthenticationError is raised if the authenticator fails.
    """
    # 1. Configure the mock authenticator to raise an error
    mock_auth = AsyncMock()
    mock_auth.get_access_token_for_user = AsyncMock(side_effect=GraphAuthError("Invalid credentials"))
    mocker.patch(
        'app.services.graph_client.delegated_auth_client',
        mock_auth
    )
    
    # 2. Instantiate the client (the transport doesn't matter as it won't be reached)
    async with httpx.AsyncClient() as http_client:
        graph_client = GraphClient(http_client=http_client)

        # 3. Assert that the correct exception is raised
        with pytest.raises(GraphClientAuthenticationError):
            await graph_client.fetch_messages(mailbox="me")


@pytest.mark.asyncio
async def test_fetch_messages_api_failure(mock_authenticator):
    """
    Tests that GraphAPIFailedRequest is raised when the Graph API returns an error (e.g., 404).
    """
    # 1. Define a transport that returns a 404 Not Found error
    transport = httpx.MockTransport(
        lambda request: httpx.Response(404, text="User not found")
    )

    async with httpx.AsyncClient(transport=transport) as http_client:
        graph_client = GraphClient(http_client=http_client)

        with pytest.raises(GraphAPIFailedRequest, match="Graph API returned status 404"):
            await graph_client.fetch_messages(mailbox="me")


@pytest.mark.asyncio
async def test_fetch_eml_content_success(mock_authenticator):
    """
    Tests successful fetching of raw .eml content.
    """
    eml_content = b"From: test\nSubject: Hello"
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=eml_content)
    )

    async with httpx.AsyncClient(transport=transport) as http_client:
        graph_client = GraphClient(http_client=http_client)
        
        content: bytes = await graph_client.fetch_eml_content(
            message_id="test-id",
            mailbox="me"
        )

        assert content == eml_content
        mock_authenticator.get_access_token_for_user.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_eml_content_api_failure(mock_authenticator):
    """
    Tests that GraphAPIFailedRequest is raised for a non-200 response.
    """
    transport = httpx.MockTransport(
        lambda request: httpx.Response(500, text="Internal Server Error")
    )

    async with httpx.AsyncClient(transport=transport) as http_client:
        graph_client = GraphClient(http_client=http_client)

        with pytest.raises(GraphAPIFailedRequest, match="Graph API returned status 500"):
            await graph_client.fetch_eml_content(message_id="test-id", mailbox="me")