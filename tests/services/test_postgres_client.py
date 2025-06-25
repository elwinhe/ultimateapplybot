"""
tests/services/test_postgres_client.py

Unit tests for the PostgresClient service.

Test the PostgresClient's logic
in isolation.
"""
from __future__ import annotations

import asyncpg
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

# Import the client and its exceptions for testing
from app.services.postgres_client import (
    PostgresClient,
    PostgresConnectionError,
)


# Test Setup
@pytest.fixture(autouse=True)
def mock_asyncpg(mocker):
    """Mocks the entire asyncpg library."""
    return mocker.patch('app.services.postgres_client.asyncpg')


# Tests for Initialization

@pytest.mark.asyncio
async def test_client_initialize_success(mock_asyncpg):
    """
    Tests that the client initializes the connection pool and validates the connection.
    """
    # 1. Configure the mock to simulate successful connection and execution
    mock_pool = MagicMock()
    mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
    
    # Mock the connection context manager
    mock_connection = AsyncMock()
    mock_acquire_cm = MagicMock()
    mock_acquire_cm.__aenter__ = AsyncMock(return_value=mock_connection)
    mock_acquire_cm.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire.return_value = mock_acquire_cm
    mock_connection.execute = AsyncMock()

    # 2. Instantiate and initialize the client
    client = PostgresClient()
    await client.initialize()

    # 3. Assert that the pool was created and the validation query was run
    mock_asyncpg.create_pool.assert_awaited_once()
    assert client._pool is not None
    mock_connection.execute.assert_awaited_once_with("SELECT 1")


@pytest.mark.asyncio
async def test_client_initialize_failure(mock_asyncpg):
    """
    Tests that PostgresConnectionError is raised if pool creation fails.
    """
    # 1. Configure the mock to raise an exception
    mock_asyncpg.create_pool = AsyncMock(side_effect=OSError("Connection refused"))

    # 2. Assert that the correct exception is raised
    client = PostgresClient()
    with pytest.raises(PostgresConnectionError, match="Could not establish connection"):
        await client.initialize()


# Tests for Database Operations
@pytest_asyncio.fixture
async def initialized_client(mock_asyncpg) -> PostgresClient:
    """Provides a client that is already initialized with a mock pool."""
    mock_pool = MagicMock()
    mock_asyncpg.create_pool = AsyncMock(return_value=mock_pool)
    
    # Mock the connection context manager
    mock_connection = AsyncMock()
    mock_acquire_cm = MagicMock()
    mock_acquire_cm.__aenter__ = AsyncMock(return_value=mock_connection)
    mock_acquire_cm.__aexit__ = AsyncMock(return_value=None)
    mock_pool.acquire.return_value = mock_acquire_cm
    mock_connection.execute = AsyncMock()
    
    client = PostgresClient()
    await client.initialize()
    return client


@pytest.mark.asyncio
async def test_execute_success(initialized_client: PostgresClient):
    """
    Tests that the execute method correctly runs a query.
    """
    # 1. Get the mock connection from the mock pool
    mock_acquire_cm = initialized_client._pool.acquire.return_value
    mock_connection = mock_acquire_cm.__aenter__.return_value
    mock_connection.execute.return_value = "CREATE TABLE"

    # 2. Call the method and assert the result
    query = "CREATE TABLE users (id int);"
    status = await initialized_client.execute(query)

    assert status == "CREATE TABLE"
    mock_connection.execute.assert_awaited_with(query)


@pytest.mark.asyncio
async def test_fetch_one_success(initialized_client: PostgresClient):
    """
    Tests that the fetch_one method correctly retrieves a single record.
    """
    mock_record = MagicMock()
    mock_record.get.return_value = "test_user"
    
    mock_acquire_cm = initialized_client._pool.acquire.return_value
    mock_connection = mock_acquire_cm.__aenter__.return_value
    mock_connection.fetchrow = AsyncMock(return_value=mock_record)
    
    query = "SELECT * FROM users WHERE id = $1;"
    record = await initialized_client.fetch_one(query, 1)

    assert record is not None
    assert record.get("username") == "test_user" # Example of how to use a mock record
    mock_connection.fetchrow.assert_awaited_with(query, 1)


@pytest.mark.asyncio
async def test_fetch_all_success(initialized_client: PostgresClient):
    """
    Tests that the fetch_all method correctly retrieves a list of records.
    """
    mock_records = [MagicMock(), MagicMock()]
    mock_acquire_cm = initialized_client._pool.acquire.return_value
    mock_connection = mock_acquire_cm.__aenter__.return_value
    mock_connection.fetch = AsyncMock(return_value=mock_records)

    query = "SELECT * FROM users;"
    records = await initialized_client.fetch_all(query)

    assert len(records) == 2
    mock_connection.fetch.assert_awaited_with(query)


@pytest.mark.asyncio
async def test_operation_fails_when_pool_is_not_initialized():
    """
    Tests that an error is raised if an operation is attempted before initialization.
    """
    client = PostgresClient() # Not initialized
    with pytest.raises(PostgresConnectionError, match="Connection pool not initialized"):
        await client.execute("SELECT 1;")


@pytest.mark.asyncio
async def test_operation_raises_postgres_error_on_db_failure(initialized_client: PostgresClient):
    """
    Tests that a database-level error is caught and re-raised as a custom exception.
    """
    # 1. Configure the mock connection to raise a library-specific error
    mock_acquire_cm = initialized_client._pool.acquire.return_value
    mock_connection = mock_acquire_cm.__aenter__.return_value
    mock_connection.execute = AsyncMock(side_effect=asyncpg.PostgresError("Syntax error"))

    # 2. Assert that our custom error is raised
    with pytest.raises(PostgresConnectionError, match="Query execution failed"):
        await initialized_client.execute("SELECT FOO BAR;")
