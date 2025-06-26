"""
tests/unit/api/v1/test_auth_router.py

Unit tests for the user authentication API router.

This suite tests the auth router in isolation by mocking the
DelegatedGraphAuthenticator dependency. It verifies that the /login and /callback
endpoints correctly handle redirection, token acquisition, and errors.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# The router and dependency to be tested
from app.api.v1.auth_router import get_auth_client, router as auth_router
from app.auth.graph_auth import DelegatedGraphAuthenticator, GraphAuthError


# Test Application Setup

@pytest.fixture
def test_app() -> FastAPI:
    """Creates a minimal FastAPI app instance including only the auth router."""
    app = FastAPI()
    app.include_router(auth_router)
    return app


@pytest.fixture
def mock_auth_client() -> AsyncMock:
    """Provides a mock of the DelegatedGraphAuthenticator service."""
    return AsyncMock(spec=DelegatedGraphAuthenticator)


@pytest.fixture
def client(test_app: FastAPI, mock_auth_client: AsyncMock) -> TestClient:
    """
    Provides a FastAPI TestClient with the DelegatedGraphAuthenticator
    dependency overridden for isolated testing.
    """
    test_app.dependency_overrides[get_auth_client] = lambda: mock_auth_client
    with TestClient(test_app) as client:
        yield client
    test_app.dependency_overrides.clear()


# Test Cases

def test_login_redirects_successfully(client: TestClient, mock_auth_client: AsyncMock):
    """
    Tests that the /login endpoint correctly generates an auth URL from the
    service and returns a 307 Temporary Redirect response.
    """
    expected_auth_url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?..."
    mock_auth_client.get_auth_flow_url.return_value = expected_auth_url

    response = client.get("/auth/login", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == expected_auth_url
    mock_auth_client.get_auth_flow_url.assert_called_once()


@pytest.mark.asyncio
async def test_callback_success(client: TestClient, mock_auth_client: AsyncMock):
    """
    Tests the happy path for the /callback endpoint where the auth code is
    successfully exchanged for a token.
    """
    # 1. Arrange: The mock's acquire_token method will do nothing on success
    mock_auth_client.acquire_token_by_auth_code = AsyncMock()

    # 2. Act
    response = client.get("/auth/callback?code=valid-auth-code")

    # 3. Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "Authentication successful" in data["message"]
    mock_auth_client.acquire_token_by_auth_code.assert_awaited_once_with("valid-auth-code")


@pytest.mark.asyncio
async def test_callback_handles_auth_error(client: TestClient, mock_auth_client: AsyncMock):
    """
    Tests that if the authenticator service raises a GraphAuthError, the
    endpoint catches it and returns a 400 Bad Request.
    """
    error_message = "Invalid authorization code."
    mock_auth_client.acquire_token_by_auth_code = AsyncMock(
        side_effect=GraphAuthError(error_message)
    )

    response = client.get("/auth/callback?code=invalid-code")

    assert response.status_code == 400
    data = response.json()
    assert "Authentication failed" in data["detail"]
    assert error_message in data["detail"]


def test_callback_handles_invalid_code_format(client: TestClient):
    """
    Tests that the endpoint's internal validation catches a malformed code
    before it even reaches the service layer.
    """
    # Act: Make a request with a very short, invalid code
    response = client.get("/auth/callback?code=short")

    # Assert
    assert response.status_code == 400
    assert "Invalid authorization code format" in response.json()["detail"]
