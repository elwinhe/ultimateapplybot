"""
app/api/v1/email.py

FastAPI router for handling email-related HTTP endpoints.
"""
import logging
from datetime import datetime
from typing import List, Optional, Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from fastapi.responses import JSONResponse

from app.models.email import Email
from app.services.graph_client import (GraphAPIFailedRequest, GraphClient, GraphClientError)
from app.config import settings
from app.celery_app import celery

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/emails",
    tags=["Emails"],
)

# Security scheme for JWT authentication
security = HTTPBearer()

# Dependency Injection
def get_graph_client(request: Request) -> GraphClient:
    """Dependency provider for the GraphClient."""
    try:
        return GraphClient(http_client=request.app.state.http_client)
    except AttributeError:
        logger.critical("httpx.AsyncClient not found in app state. Is lifespan configured?")
        raise HTTPException(status_code=500, detail="Server is not configured correctly.")

async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """
    Extract and validate user ID from JWT token.
    
    Args:
        credentials: Bearer token from Authorization header
        
    Returns:
        User ID from validated JWT token
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    try:
        # Decode and validate JWT token
        payload = jwt.decode(
            credentials.credentials, 
            settings.JWT_SECRET_KEY, 
            algorithms=["HS256"]
        )
        
        # Extract user_id from token claims
        user_id = payload.get("sub")  # Standard JWT claim for subject
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token: missing user ID")
            
        return user_id
        
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")


# API Endpoint Definition 
@router.post("/process")
async def trigger_email_processing() -> JSONResponse:
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


@router.get("/tasks/{task_id}")
async def get_task_status(task_id: str) -> JSONResponse:
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


@router.get(
    "/me",
    response_model=List[Email],
    summary="Fetch recent emails for the authenticated user",
)
async def get_my_emails(
    # This dependency provides the user ID from the request's auth token
    current_user_id: Annotated[str, Depends(get_current_user_id)],
    # This dependency provides the GraphClient
    client: Annotated[GraphClient, Depends(get_graph_client)],
    top: int = Query(default=10, ge=1, le=100),
    since: Optional[datetime] = Query(default=None),
) -> List[Email]:
    """
    Retrieves a list of recent emails for the currently authenticated user.
    The user's identity is determined from their authentication token.
    """
    logger.info("Fetching top %d emails for user_id: %s", top, current_user_id)
    try:
        # Pass the dynamically retrieved user_id to the service layer
        emails = await client.fetch_messages(
            user_id=current_user_id,
            top=top,
            since=since
        )
        return emails
    except GraphAPIFailedRequest as e:
        logger.error("Graph API request failed for user %s: %s", current_user_id, str(e), exc_info=True)
        raise HTTPException(status_code=502, detail=f"Error from Microsoft Graph API: {str(e)}") from e
    except GraphClientError as e:
        logger.error("GraphClient error for user %s: %s", current_user_id, str(e), exc_info=True)
        raise HTTPException(status_code=500, detail=f"Email service error: {str(e)}") from e