"""
app/api/v1/email.py

FastAPI router for handling email-related HTTP endpoints.
Follows Endeavor AI standards for API design, dependency injection, and error handling.
"""
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import AsyncGenerator, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

# Qualified Internal Imports
from app.config import settings
from app.models.email import Email
from app.services.graph_client import (GraphAPIFailedRequest, GraphClient, GraphClientError)

logger = logging.getLogger(__name__)

# APIRouter for version v1 of the email API
router = APIRouter(
    prefix="/emails",
    tags=["Emails"],
)

# Dependency Injection
def get_graph_client(request: Request) -> GraphClient:
    """
    Dependency that provides a GraphClient instance.

    It retrieves the shared httpx.AsyncClient from the application state,
    ensuring a single, managed client is used for all requests.
    """
    try:
        # The http_client is attached to the app state by the lifespan manager
        return GraphClient(http_client=request.app.state.http_client)
    except AttributeError:
        logger.critical("httpx.AsyncClient not found in app state. Is the lifespan manager configured?")
        raise HTTPException(status_code=500, detail="Server is not configured correctly.")

# API Endpoint Definition
@router.get(
    "/{user_id}",
    response_model=List[Email],
    summary="Fetch recent emails for a specific user",
)

async def get_emails_for_user(
    # Path & Query Parameters
    user_id: str = Path(
        ...,
        description="The user principal name (e.g., user@example.com) or ID of the user.",
        examples=["adele.vance@contoso.com"]
    ),
    top: int = Query(
        default=10,
        ge=1,
        le=100,
        description="Number of emails to return (between 1 and 100).",
    ),
    since: Optional[datetime] = Query(
        default=None,
        description="Fetch emails received after this ISO 8601 timestamp.",
    ),
    client: GraphClient = Depends(get_graph_client),
):
    """
    Retrieves a list of recent emails for a specified user, sorted from newest to oldest.
    """
    logger.info("Fetching top %d emails for user_id: %s", top, user_id)
    try:
        emails = await client.fetch_messages(
            mailbox=user_id,
            top=top,
            since=since
        )
        return emails

    except GraphAPIFailedRequest as e:
        logger.error("Graph API request failed for user %s: %s", user_id, str(e), exc_info=True)
        # 502 Bad Gateway is appropriate for an error from an upstream service
        raise HTTPException(status_code=502, detail=f"Error from Microsoft Graph API: {str(e)}") from e
    except GraphClientError as e:
        logger.error("GraphClient error for user %s: %s", user_id, str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Email service error: {str(e)}") from e
    except Exception as e:
        # Catch-all for truly unexpected errors
        logger.exception("An unexpected error occurred while fetching emails for user %s", user_id)
        raise HTTPException(status_code=500, detail="An unexpected internal error occurred.")
