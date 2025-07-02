"""
/tests/integration/test_postgres_integration.py

Integration tests for the PostgresClient service.

These tests connect to the PostgreSQL service defined in the docker-compose.yml,
ensuring the client works against a live database instance.
Updated for multi-user architecture.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from collections.abc import AsyncGenerator

# Import the client AND the helper functions to be tested
from app.services.postgres_client import PostgresClient, store_refresh_token, get_refresh_token
import app.services.postgres_client as pg_mod
from app.config import Settings

@pytest_asyncio.fixture
async def live_postgres_client() -> AsyncGenerator[PostgresClient, None]:
    """
    Provides an initialized PostgresClient connected to the dedicated test database,
    using the application's central configuration mechanism.
    """
    # 1. Create a new Settings object within the test context.
    # This will load environment variables set by the test-runner service.
    test_settings = Settings()

    # 2. Create and initialize a new client instance pointed at the test DB.
    client = PostgresClient(db_url=test_settings.DATABASE_URL)
    await client.initialize()

    # 3. Create tables if they don't exist in the test DB.
    await client.create_tables()

    # 4. Before yielding the client, clean the tables.
    pg_mod.postgres_client = client
    await client.execute("TRUNCATE TABLE archived_emails, auth_tokens RESTART IDENTITY CASCADE;")
    
    # 5. Yield the client to the test function
    yield client

    # 6. After the test completes, close the client's connection pool.
    await client.close()

@pytest.mark.asyncio
async def test_create_and_fetch_archived_email(live_postgres_client: PostgresClient):
    """
    Tests the full save-and-retrieve cycle for email metadata.
    """
    # 1. Define the data to be saved
    message_id = "test-message-id-12345"
    subject = "Your Test Invoice"
    s3_key = "emails/test-message-id-12345.eml"

    # 2. Execute the INSERT query
    insert_query = """
        INSERT INTO archived_emails (message_id, subject, s3_key)
        VALUES ($1, $2, $3);
    """
    await live_postgres_client.execute(insert_query, message_id, subject, s3_key)

    # 3. Execute the SELECT query to retrieve the data
    fetch_query = "SELECT * FROM archived_emails WHERE message_id = $1;"
    record = await live_postgres_client.fetch_one(fetch_query, message_id)

    # 4. Assert that the retrieved data matches what was saved
    assert record is not None
    assert record["message_id"] == message_id
    assert record["subject"] == subject
    assert record["s3_key"] == s3_key

@pytest.mark.asyncio
async def test_fetch_one_returns_none_for_nonexistent_record(live_postgres_client: PostgresClient):
    """
    Tests that fetch_one correctly returns None when no record is found.
    """
    record = await live_postgres_client.fetch_one(
        "SELECT * FROM archived_emails WHERE message_id = $1;",
        "nonexistent-id"
    )
    assert record is None

# --- Tests for Multi-User Auth Token Storage ---

@pytest.mark.asyncio
async def test_create_and_fetch_auth_token(live_postgres_client: PostgresClient):
    """
    Tests the full save-and-retrieve cycle for user authentication tokens.
    """
    # 1. Define the data to be saved
    user_id = "test-user@example.com"
    encrypted_refresh_token = "encrypted_token_for_test_user"

    # 2. Execute the INSERT query
    insert_query = """
        INSERT INTO auth_tokens (user_id, encrypted_refresh_token)
        VALUES ($1, $2);
    """
    await live_postgres_client.execute(insert_query, user_id, encrypted_refresh_token)

    # 3. Execute the SELECT query to retrieve the data
    fetch_query = "SELECT * FROM auth_tokens WHERE user_id = $1;"
    record = await live_postgres_client.fetch_one(fetch_query, user_id)

    # 4. Assert that the retrieved data matches what was saved
    assert record is not None
    assert record["user_id"] == user_id
    assert record["encrypted_refresh_token"] == encrypted_refresh_token

@pytest.mark.asyncio
async def test_fetch_all_auth_tokens(live_postgres_client: PostgresClient):
    """
    Tests fetching all authenticated users (multi-user scenario).
    """
    # 1. Insert multiple test users
    test_users = [
        ("user1@example.com", "token1"),
        ("user2@example.com", "token2"),
        ("user3@example.com", "token3")
    ]
    
    for user_id, token in test_users:
        await live_postgres_client.execute(
            "INSERT INTO auth_tokens (user_id, encrypted_refresh_token) VALUES ($1, $2);",
            user_id, token
        )

    # 2. Fetch all users
    records = await live_postgres_client.fetch_all("SELECT user_id FROM auth_tokens;")
    
    # 3. Assert that all users are returned
    assert len(records) == 3
    user_ids = [record["user_id"] for record in records]
    assert "user1@example.com" in user_ids
    assert "user2@example.com" in user_ids
    assert "user3@example.com" in user_ids

@pytest.mark.asyncio
async def test_auth_token_upsert_behavior(live_postgres_client: PostgresClient):
    """
    Tests that auth tokens can be updated (upsert behavior).
    """
    user_id = "upsert-test@example.com"
    initial_token = "initial_token"
    updated_token = "updated_token"

    # 1. Insert initial token
    await live_postgres_client.execute(
        "INSERT INTO auth_tokens (user_id, encrypted_refresh_token) VALUES ($1, $2);",
        user_id, initial_token
    )

    # 2. Update the token
    await live_postgres_client.execute(
        "UPDATE auth_tokens SET encrypted_refresh_token = $2 WHERE user_id = $1;",
        user_id, updated_token
    )

    # 3. Verify the update
    record = await live_postgres_client.fetch_one(
        "SELECT * FROM auth_tokens WHERE user_id = $1;",
        user_id
    )
    
    assert record is not None
    assert record["encrypted_refresh_token"] == updated_token

@pytest.mark.asyncio
async def test_multi_user_archived_emails(live_postgres_client: PostgresClient):
    """
    Tests that archived emails work correctly in a multi-user scenario.
    """
    # 1. Insert emails for multiple users (simulating different users' emails)
    test_emails = [
        ("user1-email-1", "Invoice for User 1", "emails/user1-email-1.eml"),
        ("user2-email-1", "Receipt for User 2", "emails/user2-email-1.eml"),
        ("user1-email-2", "Another Invoice for User 1", "emails/user1-email-2.eml")
    ]
    
    for message_id, subject, s3_key in test_emails:
        await live_postgres_client.execute(
            "INSERT INTO archived_emails (message_id, subject, s3_key) VALUES ($1, $2, $3);",
            message_id, subject, s3_key
        )

    # 2. Fetch all archived emails
    records = await live_postgres_client.fetch_all("SELECT * FROM archived_emails ORDER BY message_id;")
    
    # 3. Assert that all emails are stored correctly
    assert len(records) == 3
    
    # Verify specific emails exist
    message_ids = [record["message_id"] for record in records]
    assert "user1-email-1" in message_ids
    assert "user2-email-1" in message_ids
    assert "user1-email-2" in message_ids

@pytest.mark.asyncio
async def test_multi_user_token_isolation(live_postgres_client: PostgresClient):
    """Ensure updating one user's token does not affect others."""
    await live_postgres_client.execute("DELETE FROM auth_tokens;")
    users = [("user1@example.com", "token1"), ("user2@example.com", "token2")]
    for user_id, token in users:
        await store_refresh_token(user_id, token)
    # Update user1's token
    await store_refresh_token("user1@example.com", "token1-updated")
    # Check both tokens
    record1 = await get_refresh_token("user1@example.com")
    record2 = await get_refresh_token("user2@example.com")
    assert record1 == "token1-updated"
    assert record2 == "token2"
