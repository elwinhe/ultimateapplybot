"""
app/services/postgres_client.py

Provides a robust client for interacting with PostgreSQL database.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

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

    This class manages the asyncpg connection pool and provides
    high-level methods for database operations.
    """

    def __init__(self) -> None:
        """Initializes the PostgreSQL client."""
        self._pool: Optional[Pool] = None
        self._connection_string: str = settings.get_database_url()

    async def initialize(self) -> None:
        """
        Initialize the connection pool.
        
        Raises:
            PostgresConnectionError: If connection pool creation fails.
        """
        try:
            self._pool = await asyncpg.create_pool(
                self._connection_string,
                min_size=1,
                max_size=10,
                command_timeout=60,
                server_settings={
                    'application_name': 'emailreader'
                }
            )
            logger.info("PostgreSQL connection pool initialized successfully")
            
            # Test the connection
            async with self._pool.acquire() as conn:
                await conn.execute("SELECT 1")
            logger.info("PostgreSQL connection test successful")
            
        except Exception as e:
            logger.critical("Failed to initialize PostgreSQL client: %s", str(e), exc_info=True)
            raise PostgresConnectionError("Could not establish connection to PostgreSQL") from e

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("PostgreSQL connection pool closed")

    @asynccontextmanager
    async def get_connection(self) -> AsyncGenerator[Connection, None]:
        """
        Get a database connection from the pool.
        
        Yields:
            Connection: An asyncpg connection object.
            
        Raises:
            PostgresConnectionError: If no connection pool is available.
        """
        if not self._pool:
            raise PostgresConnectionError("Connection pool not initialized")
        
        async with self._pool.acquire() as connection:
            yield connection

    async def execute(self, query: str, *args) -> str:
        """
        Execute a query that doesn't return results.
        
        Args:
            query: SQL query to execute.
            *args: Query parameters.
            
        Returns:
            Status message from the query execution.
            
        Raises:
            PostgresConnectionError: If query execution fails.
        """
        try:
            async with self.get_connection() as conn:
                result = await conn.execute(query, *args)
                logger.debug("Executed query: %s", query)
                return result
        except Exception as e:
            logger.error("Failed to execute query: %s", query, exc_info=True)
            raise PostgresConnectionError(f"Query execution failed: {str(e)}") from e

    async def fetch_one(self, query: str, *args) -> Optional[asyncpg.Record]:
        """
        Fetch a single row from the database.
        
        Args:
            query: SQL query to execute.
            *args: Query parameters.
            
        Returns:
            Single row as Record or None if no results.
            
        Raises:
            PostgresConnectionError: If query execution fails.
        """
        try:
            async with self.get_connection() as conn:
                result = await conn.fetchrow(query, *args)
                logger.debug("Fetched one row: %s", query)
                return result
        except Exception as e:
            logger.error("Failed to fetch one row: %s", query, exc_info=True)
            raise PostgresConnectionError(f"Fetch one failed: {str(e)}") from e

    async def fetch_all(self, query: str, *args) -> list[asyncpg.Record]:
        """
        Fetch all rows from the database.
        
        Args:
            query: SQL query to execute.
            *args: Query parameters.
            
        Returns:
            List of rows as Records.
            
        Raises:
            PostgresConnectionError: If query execution fails.
        """
        try:
            async with self.get_connection() as conn:
                result = await conn.fetch(query, *args)
                logger.debug("Fetched %d rows: %s", len(result), query)
                return result
        except Exception as e:
            logger.error("Failed to fetch all rows: %s", query, exc_info=True)
            raise PostgresConnectionError(f"Fetch all failed: {str(e)}") from e

    async def create_tables(self) -> None:
        """Create necessary database tables if they don't exist."""
        create_emails_table = """
        CREATE TABLE IF NOT EXISTS emails (
            id VARCHAR(255) PRIMARY KEY,
            subject TEXT,
            from_address VARCHAR(255),
            from_name VARCHAR(255),
            received_date_time TIMESTAMP WITH TIME ZONE,
            has_attachments BOOLEAN DEFAULT FALSE,
            body_content_type VARCHAR(50),
            body_content TEXT,
            s3_key VARCHAR(1024),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """
        
        create_attachments_table = """
        CREATE TABLE IF NOT EXISTS email_attachments (
            id VARCHAR(255) PRIMARY KEY,
            email_id VARCHAR(255) REFERENCES emails(id) ON DELETE CASCADE,
            name VARCHAR(255),
            content_type VARCHAR(100),
            size BIGINT,
            s3_key VARCHAR(1024),
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """
        
        create_archived_emails_table = """
        CREATE TABLE IF NOT EXISTS archived_emails (
            message_id VARCHAR(255) PRIMARY KEY,
            subject TEXT,
            s3_key VARCHAR(1024),
            archived_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """
        
        try:
            await self.execute(create_emails_table)
            await self.execute(create_attachments_table)
            await self.execute(create_archived_emails_table)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error("Failed to create tables: %s", str(e), exc_info=True)
            raise PostgresClientError("Failed to create database tables") from e


# Singleton instance
postgres_client = PostgresClient()