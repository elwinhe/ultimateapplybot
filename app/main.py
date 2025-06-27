"""
app/main.py

Main application entrypoint.

- Initializes the FastAPI application.
- Manages the lifecycle of shared resources (like the HTTP client).
- Registers all API routers.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.api.v1 import email as email_v1_router
from app.api.v1 import health as health_v1_router
from app.api.v1 import auth_router
from app.config import settings
from app.services.postgres_client import postgres_client
from app.celery_app import celery

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manages the application's lifespan events.
    - Creates a shared httpx.AsyncClient on startup.
    - Initializes the PostgreSQL connection pool.
    - Cleans up resources on shutdown.
    """
    logger.info("Application startup: Initializing resources...")
    # Create a single, shared HTTP client for the application's lifetime
    async with httpx.AsyncClient(timeout=60.0) as http_client:
        # Store the client in the app state to be accessed by dependencies
        app.state.http_client = http_client
        
        await postgres_client.initialize()
        
        yield
    
    logger.info("Application shutdown: Cleaning up resources...")
    await postgres_client.close()


def create_app() -> FastAPI:
    """
    Creates and configures the main FastAPI application instance.
    """
    app = FastAPI(
        title="EmailReader API",
        description="A multi-user API for processing and archiving emails.",
        version="0.1.0",
        lifespan=lifespan  # Register the lifespan manager
    )

    # Mount the health check router at the root for easy access.
    app.include_router(health_v1_router.router)

    # Mount the main v1 API router with a prefix.
    app.include_router(email_v1_router.router, prefix="/api/v1")
    
    # Mount the auth router with the v1 prefix.
    app.include_router(auth_router.router, prefix="/api/v1")

    # Add a direct email processing endpoint for manual triggering
    @app.post("/api/v1/emails/process")
    async def trigger_email_processing():
        """
        Trigger email processing for all authenticated users.
        This dispatches the multi-user email processing task via Celery.
        """
        try:
            logger.info("Triggering multi-user email processing via Celery...")
            # Dispatch the multi-user email processing task
            task = celery.send_task('app.tasks.email_tasks.dispatch_email_processing')
            return JSONResponse(
                status_code=202,  # Accepted
                content={
                    "message": "Email processing dispatched successfully",
                    "task_id": task.id,
                    "status": "processing"
                }
            )
        except Exception as e:
            logger.error(f"Failed to dispatch email processing: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to dispatch email processing: {str(e)}"
            )

    # Add a task status endpoint
    @app.get("/api/v1/tasks/{task_id}")
    async def get_task_status(task_id: str):
        """
        Get the status of a Celery task.
        """
        try:
            task_result = celery.AsyncResult(task_id)
            return JSONResponse(
                status_code=200,
                content={
                    "task_id": task_id,
                    "status": task_result.status,
                    "result": task_result.result if task_result.ready() else None
                }
            )
        except Exception as e:
            logger.error(f"Failed to get task status: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to get task status: {str(e)}"
            )

    logger.info("Application created and routers included.")
    return app


app = create_app()
