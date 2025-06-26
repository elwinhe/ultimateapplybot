"""
tests/unit/api/v1/test_health_api.py

Unit tests for the health check API endpoint.

This suite tests the health check endpoint in isolation by mocking its
dependencies (Postgres and Redis clients) to verify that it returns the
correct status codes and response bodies for different scenarios.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch
from collections.abc import Generator

import pytest
import redis
from fastapi import FastAPI
from fastapi.testclient import TestClient

# The router to be tested
from app.api.v1.health import router as health_router
from app.services.postgres_client import PostgresConnectionError


# --- Test Application Setup ---

@pytest.fixture
def test_app() -> FastAPI:
    """Creates a minimal FastAPI app instance including only the health router."""
    app = FastAPI()
    app.include_router(health_router)
    return app


@pytest.fixture
def client(test_app: FastAPI) -> Generator[TestClient, None, None]:
    """Provides a FastAPI TestClient for making requests to the test app."""
    with TestClient(test_app) as client:
        yield client


# --- Test Cases ---

def test_health_check_all_services_healthy(client: TestClient):
    """
    Tests the happy path where both Postgres and Redis are healthy.
    Expects a 200 OK response.
    """
    # We need to mock both dependencies to simulate a success state.
    with patch('app.api.v1.health.postgres_client.execute', new_callable=AsyncMock) as mock_pg_execute, \
         patch('app.api.v1.health.redis.Redis.from_url') as mock_redis:

        # Configure the redis mock to succeed
        mock_redis.return_value.ping.return_value = True

        # Make the request
        response = client.get("/healthcheck")

        # Assert the response
        assert response.status_code == 200
        data = response.json()
        assert data == {
            "status": "ok",
            "postgres_status": "ok",
            "redis_status": "ok"
        }
        mock_pg_execute.assert_awaited_once_with("SELECT 1")
        mock_redis.return_value.ping.assert_called_once()


def test_health_check_postgres_down(client: TestClient):
    """
    Tests the scenario where the PostgreSQL connection fails.
    Expects a 503 Service Unavailable response.
    """
    with patch('app.api.v1.health.postgres_client.execute', new_callable=AsyncMock) as mock_pg_execute, \
         patch('app.api.v1.health.redis.Redis.from_url') as mock_redis:

        # Configure the postgres mock to fail
        mock_pg_execute.side_effect = PostgresConnectionError("Database connection failed")
        # Configure the redis mock to succeed
        mock_redis.return_value.ping.return_value = True

        response = client.get("/healthcheck")

        assert response.status_code == 503
        data = response.json()
        assert data["detail"] == {
            "status": "error",
            "postgres_status": "error",
            "redis_status": "ok"
        }


def test_health_check_redis_down(client: TestClient):
    """
    Tests the scenario where the Redis connection fails.
    Expects a 503 Service Unavailable response.
    """
    with patch('app.api.v1.health.postgres_client.execute', new_callable=AsyncMock) as mock_pg_execute, \
         patch('app.api.v1.health.redis.Redis.from_url') as mock_redis:

        # Configure the postgres mock to succeed
        mock_pg_execute.return_value = None
        # Configure the redis mock to fail
        mock_redis.return_value.ping.side_effect = redis.exceptions.ConnectionError

        response = client.get("/healthcheck")

        assert response.status_code == 503
        data = response.json()
        assert data["detail"] == {
            "status": "error",
            "postgres_status": "ok",
            "redis_status": "error"
        }


def test_health_check_both_services_down(client: TestClient):
    """
    Tests the scenario where both PostgreSQL and Redis connections fail.
    Expects a 503 Service Unavailable response.
    """
    with patch('app.api.v1.health.postgres_client.execute', new_callable=AsyncMock) as mock_pg_execute, \
         patch('app.api.v1.health.redis.Redis.from_url') as mock_redis:

        # Configure both mocks to fail
        mock_pg_execute.side_effect = PostgresConnectionError("Database connection failed")
        mock_redis.return_value.ping.side_effect = redis.exceptions.ConnectionError

        response = client.get("/healthcheck")

        assert response.status_code == 503
        data = response.json()
        assert data["detail"] == {
            "status": "error",
            "postgres_status": "error",
            "redis_status": "error"
        }
