"""
app/api/v1/health.py
Health check endpoint for critical dependencies like
PostgreSQL and Redis.
"""

import logging
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
import redis

from app.services.postgres_client import postgres_client, PostgresConnectionError
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

class HealthStatus(BaseModel):
    status: str
    postgres_status: str
    redis_status: str

@router.get(
    "/healthcheck",
    tags=["Health"],
    response_model=HealthStatus,
    summary="Perform a health check of the service and its dependencies."
)
async def health_check() -> HealthStatus:
    is_healthy = True
    postgres_ok = "ok"
    redis_ok = "ok"

    # Check Postgres Connection
    try:
        # A simple query to ensure the connection is live
        await postgres_client.execute("SELECT 1")
    except PostgresConnectionError:
        logger.error("Health check failed: Could not connect to PostgreSQL.")
        postgres_ok = "error"
        is_healthy = False

    # Check Redis Connection
    try:
        redis_client = redis.Redis.from_url(settings.REDIS_URL)
        redis_client.ping()
    except redis.exceptions.ConnectionError:
        logger.error("Health check failed: Could not connect to Redis.")
        redis_ok = "error"
        is_healthy = False

    if is_healthy:
        return HealthStatus(status="ok", postgres_status=postgres_ok, redis_status=redis_ok)
    else:
        # Return a 503 Service Unavailable if any dependency is down
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "error", "postgres_status": postgres_ok, "redis_status": redis_ok}
        )
