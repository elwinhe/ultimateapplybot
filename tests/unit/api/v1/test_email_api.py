"""
tests/unit/api/v1/test_email_api.py

Unit tests for the email API router (multi-user, JWT-based).

This suite tests the API layer in isolation by mocking the service-layer
and authentication dependencies, verifying endpoint behavior under various
conditions (success, API failures, validation errors, and auth errors).
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from collections.abc import Generator

import pytest
from fastapi import FastAPI, status, HTTPException
from fastapi.testclient import TestClient

from app.api.v1.email import router as email_router
from app.api.v1.email import get_graph_client, get_current_user_id
from app.services.graph_client import GraphClient, GraphAPIFailedRequest, GraphClientError
from app.models.email import Email, EmailAddress, Body

# Test Setup 
app = FastAPI()
app.include_router(email_router)

TEST_USER_ID = "test-user@example.com"

@pytest.fixture
def mock_graph_client() -> AsyncMock:
    return AsyncMock(spec=GraphClient)

@pytest.fixture
def override_auth_success():
    """Dependency override for get_current_user_id that always returns a test user id."""
    return lambda: TEST_USER_ID

@pytest.fixture
def test_client(mock_graph_client: AsyncMock, override_auth_success) -> Generator[TestClient, None, None]:
    app.dependency_overrides[get_graph_client] = lambda: mock_graph_client
    app.dependency_overrides[get_current_user_id] = override_auth_success
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()

# Test Cases 
def test_get_my_emails_success(test_client: TestClient, mock_graph_client: AsyncMock):
    """Returns emails for the authenticated user."""
    mock_emails = [
        Email(
            id="test_id_123",
            subject="Test Subject",
            received_date_time=datetime.now(timezone.utc),
            body=Body(contentType="html", content="<p>Test</p>"),
            from_address=EmailAddress(address="sender@example.com"),
            to_addresses=[EmailAddress(address="recipient@example.com")],
            cc_addresses=[], bcc_addresses=[],
            has_attachments=False
        )
    ]
    mock_graph_client.fetch_messages.return_value = mock_emails
    response = test_client.get("/emails/me?top=5")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list) and len(data) == 1
    assert data[0]["id"] == "test_id_123"
    mock_graph_client.fetch_messages.assert_awaited_once_with(
        user_id=TEST_USER_ID, top=5, since=None
    )

def test_get_my_emails_with_since(test_client: TestClient, mock_graph_client: AsyncMock):
    mock_graph_client.fetch_messages.return_value = []
    since_time = "2024-01-01T00:00:00Z"
    response = test_client.get(f"/emails/me?since={since_time}")
    assert response.status_code == 200
    mock_graph_client.fetch_messages.assert_awaited_once_with(
        user_id=TEST_USER_ID, top=10, since=datetime.fromisoformat("2024-01-01T00:00:00+00:00")
    )

def test_get_my_emails_empty(test_client: TestClient, mock_graph_client: AsyncMock):
    mock_graph_client.fetch_messages.return_value = []
    response = test_client.get("/emails/me")
    assert response.status_code == 200
    assert response.json() == []

def test_get_my_emails_graph_api_failure(test_client: TestClient, mock_graph_client: AsyncMock):
    mock_graph_client.fetch_messages.side_effect = GraphAPIFailedRequest("Upstream error")
    response = test_client.get("/emails/me")
    assert response.status_code == 502
    assert "Error from Microsoft Graph API" in response.json()["detail"]

def test_get_my_emails_internal_error(test_client: TestClient, mock_graph_client: AsyncMock):
    mock_graph_client.fetch_messages.side_effect = GraphClientError("Internal error")
    response = test_client.get("/emails/me")
    assert response.status_code == 500
    assert "Email service error" in response.json()["detail"]

def test_get_my_emails_invalid_top(test_client: TestClient):
    response = test_client.get("/emails/me?top=999")
    assert response.status_code == 422

def test_get_my_emails_top_zero(test_client: TestClient):
    response = test_client.get("/emails/me?top=0")
    assert response.status_code == 422

def test_get_my_emails_invalid_since_format(test_client: TestClient):
    response = test_client.get("/emails/me?since=not-a-date")
    assert response.status_code == 422

def test_get_my_emails_defaults(test_client: TestClient, mock_graph_client: AsyncMock):
    mock_graph_client.fetch_messages.return_value = []
    response = test_client.get("/emails/me")
    assert response.status_code == 200
    mock_graph_client.fetch_messages.assert_awaited_once_with(
        user_id=TEST_USER_ID, top=10, since=None
    )

def test_get_my_emails_unauthorized(mock_graph_client: AsyncMock):
    """If the user is not authenticated, returns 401."""
    # Remove the auth override so the real dependency runs (which expects a JWT)
    app.dependency_overrides[get_graph_client] = lambda: mock_graph_client
    if get_current_user_id in app.dependency_overrides:
        del app.dependency_overrides[get_current_user_id]
    with TestClient(app) as client:
        response = client.get("/emails/me")
        assert response.status_code == 403 or response.status_code == 401
    app.dependency_overrides.clear()

def test_get_my_emails_invalid_token(mock_graph_client: AsyncMock):
    """If the auth dependency raises, returns 401."""
    def raise_auth():
        raise HTTPException(status_code=401, detail="Invalid token")
    app.dependency_overrides[get_graph_client] = lambda: mock_graph_client
    app.dependency_overrides[get_current_user_id] = raise_auth
    with TestClient(app) as client:
        response = client.get("/emails/me")
        assert response.status_code == 401
    app.dependency_overrides.clear()
