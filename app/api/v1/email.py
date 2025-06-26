"""
app/api/v1/email.py

FastAPI router for handling email-related HTTP endpoints.
Follows Endeavor AI standards for API design, dependency injection, and error handling.
"""
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

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
    "/",
    response_model=List[Email],
    summary="Fetch recent emails for the authenticated user",
)
async def get_my_emails(
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
    Retrieves a list of recent emails for the single external user who has
    authenticated with the application via the OAuth2 flow.
    """
    logger.info("Fetching top %d emails for the authenticated user.", top)
    try:
        emails = await client.fetch_messages(
            top=top,
            since=since
        )
        return emails

    except GraphAPIFailedRequest as e:
        logger.error("Graph API request failed: %s", str(e), exc_info=True)
        raise HTTPException(status_code=502, detail=f"Error from Microsoft Graph API: {str(e)}") from e
    except GraphClientError as e:
        logger.error("GraphClient error: %s", str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Email service error: {str(e)}") from e
    except Exception as e:
        logger.exception("An unexpected error occurred while fetching emails.")
        raise HTTPException(status_code=500, detail="An unexpected internal error occurred.")
