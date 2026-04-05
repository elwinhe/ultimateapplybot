"""
app/services/postgres_client.py

Provides a robust client for interacting with PostgreSQL database, including
methods for storing and retrieving authentication tokens.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from datetime import datetime

import asyncpg
from asyncpg import Connection, Pool

from app.config import settings

logger = logging.getLogger(__name__)


class PostgresClientError(Exception):
    """Base exception for PostgresClient failures."""
    pass


class PostgresConnectionError(PostgresClientError):
    """Raised when database connection fails."""
    pass


class PostgresClient:
    """
    Handles all interactions with the PostgreSQL database.
    """

    def __init__(self, db_url: str) -> None:
        """Initializes the PostgreSQL client."""
        self._pool: Optional[Pool] = None
        self._connection_string: str = db_url

    async def initialize(self) -> None:
        """Initialize the connection pool and create tables."""
        if self._pool:
            return
        try:
            logger.warning("DB_CLIENT_INIT: Connecting with DSN: %s", self._connection_string)
            self._pool = await asyncpg.create_pool(
                self._connection_string, min_size=1, max_size=10
            )
            logger.info("PostgreSQL connection pool initialized successfully")
            await self.create_tables()
        except Exception as e:
            logger.critical("Failed to initialize PostgreSQL client", exc_info=True)
            raise PostgresConnectionError("Could not establish connection to PostgreSQL") from e

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("PostgreSQL connection pool closed")

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[Connection, None]:
        """Provides a database connection from the pool."""
        if not self._pool:
            raise PostgresConnectionError("Connection pool not initialized")
        async with self._pool.acquire() as connection:
            yield connection

    async def execute(self, query: str, *params) -> None:
        """
        Executes a query with parameters, handling connection management.
        """
        try:
            async with self.get_connection() as conn:
                return await conn.execute(query, *params)
        except Exception as e:
            logger.error("Failed to execute query: %s", query, exc_info=True)
            raise PostgresConnectionError(f"Query execution failed: {str(e)}") from e

    async def fetch_one(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch a single row from the database."""
        try:
            async with self.get_connection() as conn:
                return await conn.fetchrow(query, *args)
        except Exception as e:
            logger.error("Failed to fetch one row: %s", query, exc_info=True)
            raise PostgresConnectionError(f"Fetch one failed: {str(e)}") from e
            
    async def fetch_all(self, query: str, *args) -> list[asyncpg.Record]:
        """Fetch all rows from the database."""
        try:
            async with self.get_connection() as conn:
                return await conn.fetch(query, *args)
        except Exception as e:
            logger.error("Failed to fetch all rows: %s", query, exc_info=True)
            raise PostgresConnectionError(f"Fetch all failed: {str(e)}") from e

    async def create_tables(self) -> None:
        """Create necessary database tables if they don't exist."""
        create_auth_tokens_table = """
        CREATE TABLE IF NOT EXISTS auth_tokens (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(255) UNIQUE NOT NULL,
            access_token TEXT NOT NULL,
            refresh_token TEXT,
            expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
            scope TEXT,
            last_seen_timestamp TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        """
        add_last_seen_column = """
        ALTER TABLE auth_tokens
        ADD COLUMN IF NOT EXISTS last_seen_timestamp TIMESTAMPTZ;
        """
        add_provider_column = """
        ALTER TABLE auth_tokens
        ADD COLUMN IF NOT EXISTS provider VARCHAR(255);
        """
        try:
            await self.execute(create_auth_tokens_table)
            await self.execute(add_last_seen_column)
            await self.execute(add_provider_column)
            logger.info("Database tables checked/created successfully.")
        except Exception as e:
            logger.error("Failed to create tables", exc_info=True)
            raise PostgresClientError("Failed to create database tables") from e

# Singleton instance
postgres_client = PostgresClient(db_url=settings.DATABASE_URL)

# Token Storage Functions
async def store_refresh_token(user_id: str, refresh_token: str, user_email: str = None, access_token: str = None) -> None:
    """Stores or updates a user's refresh token in the database."""
    # Set expiration to 90 days from now (typical for refresh tokens)
    expires_at = "NOW() + interval '90 days'"
    
    await postgres_client.execute(
        """
        INSERT INTO auth_tokens (user_id, access_token, refresh_token, expires_at, scope, last_seen_timestamp, updated_at, provider, user_email)
        VALUES ($1, $2, $3, """ + expires_at + """, 'Mail.Read offline_access', NOW(), NOW(), 'microsoft', $4)
        ON CONFLICT (user_id, user_email, provider) DO UPDATE SET 
            access_token = EXCLUDED.access_token,
            refresh_token = EXCLUDED.refresh_token, 
            expires_at = EXCLUDED.expires_at,
            updated_at = NOW(),
            last_seen_timestamp = NOW();
        """,
        user_id, access_token or "", refresh_token, user_email
    )

async def get_refresh_token(user_id: str) -> Optional[str]:
    """Retrieves a user's refresh token from the database."""
    row = await postgres_client.fetch_one(
        "SELECT refresh_token FROM auth_tokens WHERE user_id = $1",
        user_id
    )
    return row["refresh_token"] if row else None
