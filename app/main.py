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
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import email as email_v1_router
from app.api.v1 import health as health_v1_router
from app.api.v1 import auth_router
from app.api.v1 import user_auth
from app.api.v1 import jobs as jobs_v1_router
from app.api.v1 import activity as activity_v1_router
from app.api.v1 import settings as settings_v1_router
from app.api.v1 import integrations as integrations_v1_router
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
    
    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",  # Local development
            "http://localhost:5173",  # Vite default port
            "http://localhost:8080",  # Vite alternative port
            "http://localhost:8081",  # Vite alternative port
            "https://career-pilot-dash.vercel.app",  # Production frontend
            # Add your production frontend URL here
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount the health check router at the root for easy access.
    app.include_router(health_v1_router.router)

    # Mount all v1 API routers with prefix
    app.include_router(email_v1_router.router, prefix="/api/v1")
    app.include_router(auth_router.router, prefix="/api/v1")
    app.include_router(user_auth.router, prefix="/api/v1")
    app.include_router(jobs_v1_router.router, prefix="/api/v1")
    app.include_router(activity_v1_router.router, prefix="/api/v1")
    app.include_router(settings_v1_router.router, prefix="/api/v1")
    app.include_router(integrations_v1_router.router, prefix="/api/v1")

    logger.info("Application created and routers included.")
    return app


app = create_app()
