"""
tests/unit/auth/test_auth_router.py

Unit tests for the user authentication API router (multi-user design).

This suite tests the auth router in isolation by mocking the
DelegatedGraphAuthenticator dependency. It verifies that the /login and /callback
endpoints correctly handle redirection, token acquisition, and errors.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# The router and dependency to be tested
from app.api.v1.auth_router import get_auth_client, router as auth_router
from app.auth.graph_auth import DelegatedGraphAuthenticator, GraphAuthError


@pytest.fixture
def test_app() -> FastAPI:
    """Creates a minimal FastAPI app instance including only the auth router."""
    app = FastAPI()
    app.include_router(auth_router)
    return app


@pytest.fixture
def mock_auth_client() -> MagicMock:
    """
    Provides a mock of the DelegatedGraphAuthenticator.
    The mock is configured with both sync and async methods to match the client's interface.
    """
    mock = MagicMock(spec=DelegatedGraphAuthenticator)
    # get_auth_flow_url is a synchronous method
    mock.get_auth_flow_url = MagicMock()
    # acquire_and_store_tokens is an asynchronous method
    mock.acquire_and_store_tokens = AsyncMock()
    return mock


@pytest.fixture
def client(test_app: FastAPI, mock_auth_client: MagicMock) -> Generator[TestClient, None, None]:
    """
    Provides a FastAPI TestClient with the auth client dependency overridden.
    """
    test_app.dependency_overrides[get_auth_client] = lambda: mock_auth_client
    with TestClient(test_app) as client:
        yield client
    test_app.dependency_overrides.clear()


# --- Test Cases ---

class TestAuthRouter:
    """Test cases for the authentication router endpoints."""

    def test_login_success(self, client: TestClient, mock_auth_client: MagicMock):
        """Tests that the /login endpoint successfully returns a redirect."""
        # Arrange: Configure the mock to return a valid URL
        mock_auth_client.get_auth_flow_url.return_value = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?..."

        # Act: Make the request, disabling redirect following for this test
        response = client.get("/auth/login", follow_redirects=False)

        # Assert: Check for a 307 redirect to the correct location
        assert response.status_code == 307
        assert "login.microsoftonline.com" in response.headers["location"]
        mock_auth_client.get_auth_flow_url.assert_called_once()

    def test_login_error(self, client: TestClient, mock_auth_client: MagicMock):
        """Tests that the /login endpoint returns a 500 error if URL generation fails."""
        # Arrange: Configure the mock to raise an exception
        mock_auth_client.get_auth_flow_url.side_effect = Exception("URL generation failed")

        # Act
        response = client.get("/auth/login")

        # Assert
        assert response.status_code == 500
        assert "Failed to initiate authentication" in response.json()["detail"]

    def test_auth_callback_success(self, client: TestClient, mock_auth_client: MagicMock):
        """Tests the happy path for the /callback endpoint with form parameters."""
        # Arrange: The async method should return successfully
        mock_auth_client.acquire_and_store_tokens.return_value = None

        # Act: POST with form data
        response = client.post(
            "/auth/callback",
            data={
                "code": "valid_auth_code_12345",
                "id_token": "valid_id_token_67890"
            }
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "Authentication successful" in data["message"]
        mock_auth_client.acquire_and_store_tokens.assert_awaited_once_with(
            "valid_auth_code_12345", "valid_id_token_67890"
        )

    def test_auth_callback_auth_error(self, client: TestClient, mock_auth_client: MagicMock):
        """Tests that a GraphAuthError from the service is handled as a 400."""
        # Arrange: Configure the mock to raise a specific application error
        mock_auth_client.acquire_and_store_tokens.side_effect = GraphAuthError("Invalid code")

        # Act
        response = client.post(
            "/auth/callback",
            data={
                "code": "invalid_code",
                "id_token": "invalid_id_token"
            }
        )

        # Assert
        assert response.status_code == 400
        assert "Invalid code" in response.json()["detail"]

    def test_auth_callback_missing_code(self, client: TestClient):
        """Tests that a missing 'code' form parameter results in a 422 validation error."""
        response = client.post(
            "/auth/callback",
            data={"id_token": "some_token"}
        )
        assert response.status_code == 422

    def test_auth_callback_missing_id_token(self, client: TestClient):
        """Tests that a missing 'id_token' form parameter results in a 422 validation error."""
        response = client.post(
            "/auth/callback",
            data={"code": "some_code"}
        )
        assert response.status_code == 422

    def test_auth_callback_missing_both_parameters(self, client: TestClient):
        """Tests that missing both 'code' and 'id_token' parameters results in a 422 validation error."""
        response = client.post("/auth/callback")
        assert response.status_code == 422

    def test_auth_callback_empty_parameters(self, client: TestClient):
        """Tests that empty form parameters are handled correctly."""
        response = client.post(
            "/auth/callback",
            data={"code": "", "id_token": ""}
        )
        # FastAPI accepts empty strings as valid form parameters
        # The validation should happen in the business logic, not at the API level
        assert response.status_code == 200

    def test_auth_callback_wrong_method(self, client: TestClient):
        """Tests that GET requests to /callback are not allowed."""
        response = client.get("/auth/callback?code=test&id_token=test")
        assert response.status_code == 405  # Method Not Allowed 