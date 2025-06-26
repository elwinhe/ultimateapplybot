"""
tests/integration/test_heath_api.py

Integration tests for the health check API endpoint.

These tests verify that the health check endpoint correctly reports the status
of critical dependencies (PostgreSQL and Redis) and returns appropriate HTTP
status codes based on service availability.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from unittest.mock import patch, MagicMock
import redis

from app.main import create_app
from app.services.postgres_client import PostgresConnectionError


@pytest_asyncio.fixture
async def test_app():
    """
    Creates a test FastAPI application instance.
    
    This fixture provides a clean application instance for each test,
    ensuring isolation between test cases.
    """
    app = create_app()
    return app


@pytest_asyncio.fixture
async def test_client(test_app):
    """
    Creates a test client for making HTTP requests to the application.
    
    This fixture provides a test client that can be used to make requests
    to the FastAPI application without starting a full server.
    """
    from fastapi.testclient import TestClient
    
    with TestClient(test_app) as client:
        yield client


def test_health_check_all_services_healthy(test_client):
    """
    Test Case 1: All Services Healthy
    
    Goal: Verify that the endpoint returns a 200 OK status when all dependencies 
    (Postgres, Redis) are running correctly.
    
    Act: Make a GET request to the /healthcheck endpoint.
    
    Assert:
        - The response status code is 200.
        - The JSON body is {"status": "ok", "postgres_status": "ok", "redis_status": "ok"}.
    """
    # Make a GET request to the health check endpoint
    response = test_client.get("/healthcheck")
    
    # Verify the response status code is 200 OK
    assert response.status_code == 200, (
        f"Expected status code 200, but got {response.status_code}. "
        f"Response body: {response.text}"
    )
    
    # Parse the JSON response
    health_data = response.json()
    
    # Verify the response structure and values
    assert health_data["status"] == "ok", (
        f"Expected overall status to be 'ok', but got '{health_data['status']}'"
    )
    assert health_data["postgres_status"] == "ok", (
        f"Expected postgres_status to be 'ok', but got '{health_data['postgres_status']}'"
    )
    assert health_data["redis_status"] == "ok", (
        f"Expected redis_status to be 'ok', but got '{health_data['redis_status']}'"
    )
    
    # Verify no additional fields are present
    expected_keys = {"status", "postgres_status", "redis_status"}
    actual_keys = set(health_data.keys())
    assert actual_keys == expected_keys, (
        f"Response contains unexpected keys. "
        f"Expected: {expected_keys}, Got: {actual_keys}"
    )


def test_health_check_postgres_down(test_client):
    """
    Test Case 2: Postgres is Down
    
    Goal: Verify that the endpoint returns a 503 Service Unavailable status 
    when it cannot connect to the database.
    
    Arrange: Use mocker.patch.object to make postgres_client.execute raise a PostgresConnectionError.
    
    Act: Make a GET request to the /healthcheck endpoint.
    
    Assert:
        - The response status code is 503.
        - The JSON body reflects that the postgres_status is "error".
    """
    # Mock the postgres_client.execute method to raise a connection error
    with patch('app.api.v1.health.postgres_client.execute') as mock_execute:
        mock_execute.side_effect = PostgresConnectionError("Database connection failed")
        
        # Make a GET request to the health check endpoint
        response = test_client.get("/healthcheck")
        
        # Verify the response status code is 503 Service Unavailable
        assert response.status_code == 503, (
            f"Expected status code 503, but got {response.status_code}. "
            f"Response body: {response.text}"
        )
        
        # Parse the JSON response
        health_data = response.json()["detail"]
        
        # Verify the response structure and values
        assert health_data["status"] == "error", (
            f"Expected overall status to be 'error', but got '{health_data['status']}'"
        )
        assert health_data["postgres_status"] == "error", (
            f"Expected postgres_status to be 'error', but got '{health_data['postgres_status']}'"
        )
        assert health_data["redis_status"] == "ok", (
            f"Expected redis_status to still be 'ok', but got '{health_data['redis_status']}'"
        )
        
        # Verify the mock was called with the expected query
        mock_execute.assert_called_once_with("SELECT 1")


def test_health_check_redis_down(test_client):
    """
    Test Case 3: Redis is Down
    
    Goal: Verify that the endpoint returns a 503 Service Unavailable status 
    when it cannot connect to Redis.
    
    Arrange: Use mocker.patch to make redis.Redis.from_url() raise a ConnectionError.
    
    Act: Make a GET request to the /healthcheck endpoint.
    
    Assert:
        - The response status code is 503.
        - The JSON body reflects that the redis_status is "error".
    """
    # Mock the redis connection to raise a connection error
    with patch('app.api.v1.health.redis.Redis.from_url') as mock_redis:
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.side_effect = redis.exceptions.ConnectionError("Redis connection failed")
        mock_redis.return_value = mock_redis_instance
        
        # Make a GET request to the health check endpoint
        response = test_client.get("/healthcheck")
        
        # Verify the response status code is 503 Service Unavailable
        assert response.status_code == 503, (
            f"Expected status code 503, but got {response.status_code}. "
            f"Response body: {response.text}"
        )
        
        # Parse the JSON response
        health_data = response.json()["detail"]
        
        # Verify the response structure and values
        assert health_data["status"] == "error", (
            f"Expected overall status to be 'error', but got '{health_data['status']}'"
        )
        assert health_data["postgres_status"] == "ok", (
            f"Expected postgres_status to still be 'ok', but got '{health_data['postgres_status']}'"
        )
        assert health_data["redis_status"] == "error", (
            f"Expected redis_status to be 'error', but got '{health_data['redis_status']}'"
        )


def test_health_check_both_services_down(test_client):
    """
    Test Case 4: Both Services Down
    
    Goal: Verify that the endpoint returns a 503 Service Unavailable status 
    when both PostgreSQL and Redis are unavailable.
    
    Arrange: Mock both postgres_client.execute and redis.Redis.from_url() to raise errors.
    
    Act: Make a GET request to the /healthcheck endpoint.
    
    Assert:
        - The response status code is 503.
        - The JSON body reflects that both postgres_status and redis_status are "error".
    """
    # Mock both services to fail
    with patch('app.api.v1.health.postgres_client.execute') as mock_execute, \
         patch('app.api.v1.health.redis.Redis.from_url') as mock_redis:
        
        # Configure postgres mock to fail
        mock_execute.side_effect = PostgresConnectionError("Database connection failed")
        
        # Configure redis mock to fail
        mock_redis_instance = MagicMock()
        mock_redis_instance.ping.side_effect = redis.exceptions.ConnectionError("Redis connection failed")
        mock_redis.return_value = mock_redis_instance
        
        # Make a GET request to the health check endpoint
        response = test_client.get("/healthcheck")
        
        # Verify the response status code is 503 Service Unavailable
        assert response.status_code == 503, (
            f"Expected status code 503, but got {response.status_code}. "
            f"Response body: {response.text}"
        )
        
        # Parse the JSON response
        health_data = response.json()["detail"]
        
        # Verify the response structure and values
        assert health_data["status"] == "error", (
            f"Expected overall status to be 'error', but got '{health_data['status']}'"
        )
        assert health_data["postgres_status"] == "error", (
            f"Expected postgres_status to be 'error', but got '{health_data['postgres_status']}'"
        )
        assert health_data["redis_status"] == "error", (
            f"Expected redis_status to be 'error', but got '{health_data['redis_status']}'"
        )
