"""
tests/unit/api/v1/test_email_api.py

Unit tests for the email API router.

This suite tests the API layer in isolation by mocking the service-layer
dependencies and verifying that the endpoint behaves correctly under various
conditions (e.g., success, external API failures, validation errors).
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.email import router as email_router
from app.api.v1.email import get_graph_client

from app.services.graph_client import GraphClient, GraphAPIFailedRequest, GraphClientError
from app.models.email import Email, EmailAddress, Body

    
# Test Application Setup

# Create a minimal FastAPI app instance that includes only the router being tested.
# This ensures tests are isolated to this specific component.
app = FastAPI()
app.include_router(email_router)



@pytest.fixture
def mock_graph_client() -> AsyncMock:
    """Provides a mock of the GraphClient service."""
    return AsyncMock(spec=GraphClient)

@pytest.fixture
def test_client(mock_graph_client: AsyncMock) -> Generator[TestClient, None, None]:
    """
    Provides a FastAPI TestClient with the GraphClient dependency overridden.

    This is the core of our testing strategy. Any call to the API will receive
    the `mock_graph_client` instead of creating a real one.
    """
    app.dependency_overrides[get_graph_client] = lambda: mock_graph_client
    
    with TestClient(app) as client:
        yield client
    
    # Clean up the override after the test is done to ensure test isolation
    app.dependency_overrides.clear()


# Test Cases
def test_get_my_emails_success(test_client: TestClient, mock_graph_client: AsyncMock):
    """
    Tests the happy path where emails are fetched successfully (200 OK).
    """
    # 1. Configure the mock GraphClient's method to return valid Pydantic models.
    # The API layer will automatically serialize these into JSON.
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

    # 2. Make a request to the test client
    response = test_client.get("/emails/?top=5")

    # 3. Assert the response and that the mock was called correctly
    assert response.status_code == 200
    response_data = response.json()
    assert isinstance(response_data, list)
    assert len(response_data) == 1
    assert response_data[0]['id'] == "test_id_123"

    mock_graph_client.fetch_messages.assert_awaited_once_with(
        top=5,
        since=None
    )

def test_get_my_emails_with_since_parameter(test_client: TestClient, mock_graph_client: AsyncMock):
    """
    Tests that the 'since' parameter is correctly passed to the service layer.
    """
    mock_emails = []
    mock_graph_client.fetch_messages.return_value = mock_emails
    
    # Test with ISO 8601 timestamp
    since_time = "2024-01-01T00:00:00Z"
    response = test_client.get(f"/emails/?since={since_time}")
    
    assert response.status_code == 200
    mock_graph_client.fetch_messages.assert_awaited_once_with(
        top=10,  # default value
        since=datetime.fromisoformat("2024-01-01T00:00:00+00:00")
    )

def test_get_my_emails_empty_results(test_client: TestClient, mock_graph_client: AsyncMock):
    """
    Tests that empty results are handled correctly.
    """
    mock_graph_client.fetch_messages.return_value = []
    
    response = test_client.get("/emails/")
    
    assert response.status_code == 200
    response_data = response.json()
    assert isinstance(response_data, list)
    assert len(response_data) == 0

def test_get_my_emails_handles_graph_api_failure(test_client: TestClient, mock_graph_client: AsyncMock):
    """
    Tests that a known failure from the service layer (GraphAPIFailedRequest)
    is correctly handled and returns a 502 Bad Gateway status.
    """
    mock_graph_client.fetch_messages.side_effect = GraphAPIFailedRequest("Upstream service unavailable")

    response = test_client.get("/emails/")

    assert response.status_code == 502
    assert "Error from Microsoft Graph API" in response.json()["detail"]

def test_get_my_emails_handles_internal_service_error(test_client: TestClient, mock_graph_client: AsyncMock):
    """
    Tests that a generic internal service error is handled with a 500 status.
    """
    mock_graph_client.fetch_messages.side_effect = GraphClientError("Internal logic error")

    response = test_client.get("/emails/")

    assert response.status_code == 500
    assert "Email service error" in response.json()["detail"]

def test_get_my_emails_validation_error_top_parameter(test_client: TestClient):
    """
    Tests that FastAPI's automatic request validation catches invalid 'top' parameter
    and returns a 422 Unprocessable Entity status.
    """
    response = test_client.get("/emails/?top=999")

    assert response.status_code == 422

def test_get_my_emails_validation_error_top_parameter_zero(test_client: TestClient):
    """
    Tests that FastAPI's automatic request validation catches invalid 'top' parameter
    when it's less than 1.
    """
    response = test_client.get("/emails/?top=0")

    assert response.status_code == 422

def test_get_my_emails_validation_error_invalid_since_format(test_client: TestClient):
    """
    Tests that FastAPI's automatic request validation catches invalid 'since' parameter format.
    """
    response = test_client.get("/emails/?since=invalid-date")

    assert response.status_code == 422

def test_get_my_emails_default_parameters(test_client: TestClient, mock_graph_client: AsyncMock):
    """
    Tests that default parameters are used when none are provided.
    """
    mock_graph_client.fetch_messages.return_value = []
    
    response = test_client.get("/emails/")
    
    assert response.status_code == 200
    mock_graph_client.fetch_messages.assert_awaited_once_with(
        top=10,
        since=None
    )
