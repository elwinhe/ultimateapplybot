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
from app.tasks.email_tasks import pull_and_process_emails_logic

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
        description="An API for processing and archiving emails.",
        version="0.1.0",
        lifespan=lifespan  # Register the lifespan manager
    )

    # Mount the health check router at the root for easy access.
    app.include_router(health_v1_router.router)

    # Mount the main v1 API router with a prefix.
    app.include_router(email_v1_router.router, prefix="/api/v1")
    
    # Mount the auth router with the v1 prefix.
    app.include_router(auth_router.router, prefix="/api/v1")

    # Add a direct email processing endpoint
    @app.post("/api/v1/emails/process")
    async def trigger_email_processing():
        """
        Trigger email processing directly through the main application.
        This uses the already initialized PostgreSQL connection pool.
        """
        try:
            logger.info("Triggering email processing through main application...")
            await pull_and_process_emails_logic()
            return JSONResponse(
                status_code=200,
                content={"message": "Email processing completed successfully"}
            )
        except Exception as e:
            logger.error(f"Email processing failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Email processing failed: {str(e)}"
            )

    logger.info("Application created and routers included.")
    return app


app = create_app()
