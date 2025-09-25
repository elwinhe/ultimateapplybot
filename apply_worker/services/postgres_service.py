import logging
import asyncpg
from datetime import datetime
from typing import Optional, Dict, Any
import json
import config

logger = logging.getLogger(__name__)


class PostgresService:
    """Service for interacting with PostgreSQL database."""
    
    def __init__(self):
        self.pool = None
    
    async def initialize(self):
        """Initialize database connection pool."""
        self.pool = await asyncpg.create_pool(
            config.POSTGRES_URL,
            min_size=1,
            max_size=5
        )
        logger.info("PostgreSQL connection pool initialized")
    
    async def close(self):
        """Close database connections."""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL connection pool closed")
    
    async def update_job_status(self, job_id: str, status: str):
        """Update job status in database."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE jobs 
                SET status = $1, updated_at = NOW() 
                WHERE id = $2
                """,
                status, job_id
            )
            logger.info(f"Updated job {job_id} status to {status}")
    
    async def update_job_applied(
        self, 
        job_id: str,
        job_title: Optional[str] = None,
        company: Optional[str] = None,
        location: Optional[str] = None,
        technologies: Optional[str] = None,
        seniority: Optional[str] = None
    ):
        """Update job details after successful application."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE jobs 
                SET status = 'applied',
                    title = COALESCE($2, title),
                    company = COALESCE($3, company),
                    location = COALESCE($4, location),
                    technologies = $5,
                    seniority = $6,
                    applied_at = NOW(),
                    updated_at = NOW()
                WHERE id = $1
                """,
                job_id, job_title, company, location, technologies, seniority
            )
            logger.info(f"Updated job {job_id} with application details")
    
    async def log_activity(
        self,
        user_id: str,
        activity_type: str,
        title: str,
        description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Log an activity event."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO activity_events (user_id, type, title, description, metadata, created_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                """,
                user_id, activity_type, title, description, 
                json.dumps(metadata) if metadata else '{}'
            )
            logger.debug(f"Logged activity: {activity_type} for user {user_id}")
    
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job details by ID."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM jobs WHERE id = $1",
                job_id
            )
            return dict(row) if row else None
