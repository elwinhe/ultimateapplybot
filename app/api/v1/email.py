"""
app/api/v1/email.py

FastAPI router for handling email-related HTTP endpoints.
Follows Endeavor AI standards for API design, dependency injection, and error handling.
"""

from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Path
import httpx

# Qualified internal imports
from app.services.graph_client import GraphClient
from app.models.email import Email
from app.config import settings # Centralized configuration

# Logger setup
import logging
logger = logging.getLogger(__name__)

# Define custom, typed errors for this layer
class APIValidationError(Exception):
    """Custom exception for API validation errors."""
    pass

# Dependency Injection
def get_graph_client() -> GraphClient:
    """
    Dependency provider for the GraphClient.
    Initializes the client using centralized settings.
    """
    try:
        return GraphClient(
            tenant_id=settings.TENANT_ID,
            client_id=settings.CLIENT_ID,
            client_secret=settings.CLIENT_SECRET
        )
    except ValueError as e:
        logger.critical("GraphClient initialization failed due to missing settings: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Server Configuration Error: {e}")

# APIRouter for version v1 of the email API
router = APIRouter(
    prefix="/emails",
    tags=["Emails"],
)

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
    # Dependency Injection
    client: GraphClient = Depends(get_graph_client),
):
    """
    Retrieves a list of recent emails for a specified user, sorted from newest to oldest.

    This endpoint demonstrates passing parameters through the router to the service layer,
    decoupling the API from the business logic.
    """
    logger.info("Fetching top %d emails for user_id: %s", top, user_id)
    try:
        emails = await client.fetch_messages(
            mailbox=user_id,
            top=top,
            since=since
        )
        return emails
    # Specific Exception Handling
    except httpx.HTTPStatusError as e:
        logger.error(
            "Graph API request failed for user %s: %s",
            user_id, e.response.text, exc_info=True
        )
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Error from Microsoft Graph API: {e.response.text}"
        ) from e
    except Exception as e:
        # Catch-all for unexpected errors
        logger.exception("An unexpected error occurred while fetching emails for user %s", user_id)
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected internal error occurred: {str(e)}"
        )
