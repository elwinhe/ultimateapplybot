"""
tests/integration/test_postgres_integration.py

Integration tests for the PostgresClient service.

These tests connect to the PostgreSQL service defined in the docker-compose.yml,
ensuring the client works against a live database instance.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from collections.abc import AsyncGenerator

# Import the client to be tested
from app.services.postgres_client import PostgresClient


@pytest_asyncio.fixture
async def live_postgres_client() -> AsyncGenerator[PostgresClient, None]:
    """
    Provides an initialized PostgresClient connected to the local PostgreSQL container.
    It also ensures the database tables are clean before each test.
    """
    # 1. Create and initialize a new client instance.
    client = PostgresClient()
    await client.initialize()

    # 2. Create tables if they don't exist
    await client.create_tables()

    # 3. Before yielding the client to the test, clean the tables.
    await client.execute("TRUNCATE TABLE archived_emails RESTART IDENTITY CASCADE;")
    
    # 4. Yield the client to the test function
    yield client

    # 5. After the test completes, close the client's connection pool
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