"""
tests/unit/services/test_postgres_client.py

Unit tests for the PostgresClient service (multi-user design).

Test the PostgresClient's logic in isolation, including
token storage for multi-user authentication.
"""
from __future__ import annotations

import asyncpg
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from unittest.mock import patch

# Import the client and its exceptions for testing
from app.services.postgres_client import (
    PostgresClient,
    PostgresConnectionError,
    PostgresClientError,
    store_refresh_token,
    get_refresh_token,
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
    client = PostgresClient(db_url="mock_db_url")
    await client.initialize()

    # 3. Assert that the pool was created and tables were created
    mock_asyncpg.create_pool.assert_awaited_once()
    assert client._pool is not None
    # We expect 2 calls for table creation (archived_emails, auth_tokens)
    assert mock_connection.execute.await_count == 2


@pytest.mark.asyncio
async def test_client_initialize_failure(mock_asyncpg):
    """
    Tests that PostgresConnectionError is raised if pool creation fails.
    """
    # 1. Configure the mock to raise an exception
    mock_asyncpg.create_pool = AsyncMock(side_effect=OSError("Connection refused"))

    # 2. Assert that the correct exception is raised
    client = PostgresClient(db_url="mock_db_url")
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
    
    client = PostgresClient(db_url="mock_db_url")
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
async def test_fetch_one_returns_none(initialized_client: PostgresClient):
    """
    Tests that fetch_one returns None when no records are found.
    """
    mock_acquire_cm = initialized_client._pool.acquire.return_value
    mock_connection = mock_acquire_cm.__aenter__.return_value
    mock_connection.fetchrow = AsyncMock(return_value=None)
    
    query = "SELECT * FROM users WHERE id = $1;"
    record = await initialized_client.fetch_one(query, 999)

    assert record is None
    mock_connection.fetchrow.assert_awaited_with(query, 999)


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
async def test_fetch_all_returns_empty_list(initialized_client: PostgresClient):
    """
    Tests that fetch_all returns an empty list when no records are found.
    """
    mock_acquire_cm = initialized_client._pool.acquire.return_value
    mock_connection = mock_acquire_cm.__aenter__.return_value
    mock_connection.fetch = AsyncMock(return_value=[])

    query = "SELECT * FROM users WHERE active = false;"
    records = await initialized_client.fetch_all(query)

    assert len(records) == 0
    mock_connection.fetch.assert_awaited_with(query)


@pytest.mark.asyncio
async def test_operation_fails_when_pool_is_not_initialized():
    """
    Tests that an error is raised if an operation is attempted before initialization.
    """
    client = PostgresClient(db_url="mock_db_url") # Not initialized
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


# Tests for Table Creation
@pytest.mark.asyncio
async def test_create_tables_success(initialized_client: PostgresClient):
    """
    Tests that the create_tables method creates all necessary tables.
    """
    # 1. Get the mock connection
    mock_acquire_cm = initialized_client._pool.acquire.return_value
    mock_connection = mock_acquire_cm.__aenter__.return_value
    mock_connection.execute = AsyncMock()

    # 2. Call the method
    await initialized_client.create_tables()

    # 3. Assert that both table creation queries were executed
    assert mock_connection.execute.await_count == 2
    
    # Verify the calls were made (we can't easily check the exact SQL content due to formatting)
    calls = mock_connection.execute.await_args_list
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_create_tables_failure(initialized_client: PostgresClient):
    """
    Tests that PostgresClientError is raised if table creation fails.
    """
    # 1. Configure the mock connection to raise an error
    mock_acquire_cm = initialized_client._pool.acquire.return_value
    mock_connection = mock_acquire_cm.__aenter__.return_value
    mock_connection.execute = AsyncMock(side_effect=asyncpg.PostgresError("Permission denied"))

    # 2. Assert that the correct exception is raised
    with pytest.raises(PostgresClientError, match="Failed to create database tables"):
        await initialized_client.create_tables()


# Tests for Archived Emails Table
@pytest.mark.asyncio
async def test_archived_emails_insert_success(initialized_client: PostgresClient):
    """
    Tests inserting a record into the archived_emails table.
    """
    # 1. Get the mock connection
    mock_acquire_cm = initialized_client._pool.acquire.return_value
    mock_connection = mock_acquire_cm.__aenter__.return_value
    mock_connection.execute = AsyncMock(return_value="INSERT 0 1")

    # 2. Insert a test record
    query = """
        INSERT INTO archived_emails (message_id, subject, s3_key, archived_at)
        VALUES ($1, $2, $3, NOW())
        ON CONFLICT (message_id) DO NOTHING;
    """
    result = await initialized_client.execute(query, "msg_123", "Test Subject", "s3://bucket/msg_123.eml")

    # 3. Assert the result
    assert result == "INSERT 0 1"
    mock_connection.execute.assert_awaited_with(query, "msg_123", "Test Subject", "s3://bucket/msg_123.eml")


@pytest.mark.asyncio
async def test_archived_emails_fetch_success(initialized_client: PostgresClient):
    """
    Tests fetching records from the archived_emails table.
    """
    # 1. Create mock records
    mock_record1 = MagicMock()
    mock_record1.get.side_effect = lambda key: {
        "message_id": "msg_123",
        "subject": "Test Email 1",
        "s3_key": "s3://bucket/msg_123.eml",
        "archived_at": "2025-01-15T10:30:00Z"
    }.get(key)
    
    mock_record2 = MagicMock()
    mock_record2.get.side_effect = lambda key: {
        "message_id": "msg_456",
        "subject": "Test Email 2", 
        "s3_key": "s3://bucket/msg_456.eml",
        "archived_at": "2025-01-15T11:00:00Z"
    }.get(key)

    # 2. Configure the mock connection
    mock_acquire_cm = initialized_client._pool.acquire.return_value
    mock_connection = mock_acquire_cm.__aenter__.return_value
    mock_connection.fetch = AsyncMock(return_value=[mock_record1, mock_record2])

    # 3. Fetch archived emails
    query = "SELECT * FROM archived_emails ORDER BY archived_at DESC;"
    records = await initialized_client.fetch_all(query)

    # 4. Assert the results
    assert len(records) == 2
    assert records[0].get("message_id") == "msg_123"
    assert records[1].get("message_id") == "msg_456"
    mock_connection.fetch.assert_awaited_with(query)


@pytest.mark.asyncio
async def test_archived_emails_duplicate_handling(initialized_client: PostgresClient):
    """
    Tests that the ON CONFLICT clause prevents duplicate message_id insertions.
    """
    # 1. Get the mock connection
    mock_acquire_cm = initialized_client._pool.acquire.return_value
    mock_connection = mock_acquire_cm.__aenter__.return_value
    # Simulate no rows affected (duplicate key)
    mock_connection.execute = AsyncMock(return_value="INSERT 0 0")

    # 2. Try to insert a duplicate message_id
    query = """
        INSERT INTO archived_emails (message_id, subject, s3_key, archived_at)
        VALUES ($1, $2, $3, NOW())
        ON CONFLICT (message_id) DO NOTHING;
    """
    result = await initialized_client.execute(query, "msg_123", "Duplicate Subject", "s3://bucket/msg_123.eml")

    # 3. Assert that no error was raised and no rows were inserted
    assert result == "INSERT 0 0"
    mock_connection.execute.assert_awaited_with(query, "msg_123", "Duplicate Subject", "s3://bucket/msg_123.eml")


# Tests for Token Storage Functions (Multi-User)
@pytest.mark.asyncio
async def test_store_refresh_token_success(mock_asyncpg):
    """
    Tests storing a refresh token for a user.
    """
    # Mock the global postgres_client singleton
    with patch('app.services.postgres_client.postgres_client') as mock_global_client:
        mock_global_client.execute = AsyncMock(return_value="INSERT 0 1")
        
        # Store a refresh token
        await store_refresh_token("user@example.com", "refresh_token_123")

        # Verify the correct query was executed
        expected_query = """
        INSERT INTO auth_tokens (user_id, encrypted_refresh_token, updated_at)
        VALUES ($1, $2, NOW())
        ON CONFLICT (user_id) DO UPDATE SET encrypted_refresh_token = EXCLUDED.encrypted_refresh_token, updated_at = NOW();
        """
        mock_global_client.execute.assert_awaited_with(expected_query, "user@example.com", "refresh_token_123")


@pytest.mark.asyncio
async def test_store_refresh_token_update_existing(mock_asyncpg):
    """
    Tests updating an existing refresh token for a user.
    """
    # Mock the global postgres_client singleton
    with patch('app.services.postgres_client.postgres_client') as mock_global_client:
        mock_global_client.execute = AsyncMock(return_value="UPDATE 1")
        
        # Update an existing refresh token
        await store_refresh_token("user@example.com", "new_refresh_token_456")

        # Verify the correct query was executed
        expected_query = """
        INSERT INTO auth_tokens (user_id, encrypted_refresh_token, updated_at)
        VALUES ($1, $2, NOW())
        ON CONFLICT (user_id) DO UPDATE SET encrypted_refresh_token = EXCLUDED.encrypted_refresh_token, updated_at = NOW();
        """
        mock_global_client.execute.assert_awaited_with(expected_query, "user@example.com", "new_refresh_token_456")


@pytest.mark.asyncio
async def test_store_refresh_token_multiple_users(mock_asyncpg):
    """
    Tests storing refresh tokens for multiple users.
    """
    # Mock the global postgres_client singleton
    with patch('app.services.postgres_client.postgres_client') as mock_global_client:
        mock_global_client.execute = AsyncMock(return_value="INSERT 0 1")
        
        # Store tokens for multiple users
        await store_refresh_token("user1@example.com", "token_1")
        await store_refresh_token("user2@example.com", "token_2")
        await store_refresh_token("user3@example.com", "token_3")

        # Verify all calls were made
        assert mock_global_client.execute.await_count == 3
        expected_query = """
        INSERT INTO auth_tokens (user_id, encrypted_refresh_token, updated_at)
        VALUES ($1, $2, NOW())
        ON CONFLICT (user_id) DO UPDATE SET encrypted_refresh_token = EXCLUDED.encrypted_refresh_token, updated_at = NOW();
        """
        mock_global_client.execute.assert_any_await(expected_query, "user1@example.com", "token_1")
        mock_global_client.execute.assert_any_await(expected_query, "user2@example.com", "token_2")
        mock_global_client.execute.assert_any_await(expected_query, "user3@example.com", "token_3")


@pytest.mark.asyncio
async def test_get_refresh_token_success(mock_asyncpg):
    """
    Tests retrieving a refresh token for a user.
    """
    # Create mock record
    mock_record = MagicMock()
    mock_record.__getitem__ = lambda self, key: "refresh_token_123"
    
    # Mock the global postgres_client singleton
    with patch('app.services.postgres_client.postgres_client') as mock_global_client:
        mock_global_client.fetch_one = AsyncMock(return_value=mock_record)
        
        # Get the refresh token
        token = await get_refresh_token("user@example.com")

        # Assert the result
        assert token == "refresh_token_123"
        mock_global_client.fetch_one.assert_awaited_with(
            "SELECT encrypted_refresh_token FROM auth_tokens WHERE user_id = $1",
            "user@example.com"
        )


@pytest.mark.asyncio
async def test_get_refresh_token_not_found(mock_asyncpg):
    """
    Tests retrieving a refresh token when the user doesn't exist.
    """
    # Mock the global postgres_client singleton
    with patch('app.services.postgres_client.postgres_client') as mock_global_client:
        mock_global_client.fetch_one = AsyncMock(return_value=None)
        
        # Get the refresh token for non-existent user
        token = await get_refresh_token("nonexistent@example.com")

        # Assert the result
        assert token is None
        mock_global_client.fetch_one.assert_awaited_with(
            "SELECT encrypted_refresh_token FROM auth_tokens WHERE user_id = $1",
            "nonexistent@example.com"
        )


@pytest.mark.asyncio
async def test_get_refresh_token_multiple_users(mock_asyncpg):
    """
    Tests retrieving refresh tokens for multiple users.
    """
    # Create mock records
    mock_record1 = MagicMock()
    mock_record1.__getitem__ = lambda self, key: "token_1"
    mock_record2 = MagicMock()
    mock_record2.__getitem__ = lambda self, key: "token_2"
    
    # Mock the global postgres_client singleton
    with patch('app.services.postgres_client.postgres_client') as mock_global_client:
        mock_global_client.fetch_one = AsyncMock(side_effect=[mock_record1, mock_record2, None])
        
        # Get tokens for multiple users
        token1 = await get_refresh_token("user1@example.com")
        token2 = await get_refresh_token("user2@example.com")
        token3 = await get_refresh_token("user3@example.com")

        # Assert the results
        assert token1 == "token_1"
        assert token2 == "token_2"
        assert token3 is None

        # Verify all calls were made
        assert mock_global_client.fetch_one.await_count == 3
        mock_global_client.fetch_one.assert_any_await(
            "SELECT encrypted_refresh_token FROM auth_tokens WHERE user_id = $1",
            "user1@example.com"
        )
        mock_global_client.fetch_one.assert_any_await(
            "SELECT encrypted_refresh_token FROM auth_tokens WHERE user_id = $1",
            "user2@example.com"
        )
        mock_global_client.fetch_one.assert_any_await(
            "SELECT encrypted_refresh_token FROM auth_tokens WHERE user_id = $1",
            "user3@example.com"
        )


# Tests for Error Handling
@pytest.mark.asyncio
async def test_token_storage_database_error(mock_asyncpg):
    """
    Tests that database errors during token storage are properly handled.
    """
    # Mock the global postgres_client singleton
    with patch('app.services.postgres_client.postgres_client') as mock_global_client:
        # Mock the execute method to raise PostgresConnectionError (which is what the real method would do)
        mock_global_client.execute = AsyncMock(side_effect=PostgresConnectionError("Query execution failed: Connection lost"))
        
        # Assert that the error is propagated
        with pytest.raises(PostgresConnectionError, match="Query execution failed"):
            await store_refresh_token("user@example.com", "token_123")


@pytest.mark.asyncio
async def test_token_retrieval_database_error(mock_asyncpg):
    """
    Tests that database errors during token retrieval are properly handled.
    """
    # Mock the global postgres_client singleton
    with patch('app.services.postgres_client.postgres_client') as mock_global_client:
        # Mock the fetch_one method to raise PostgresConnectionError (which is what the real method would do)
        mock_global_client.fetch_one = AsyncMock(side_effect=PostgresConnectionError("Fetch one failed: Connection lost"))
        
        # Assert that the error is propagated
        with pytest.raises(PostgresConnectionError, match="Fetch one failed"):
            await get_refresh_token("user@example.com")
