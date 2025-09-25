"""
app/api/v1/integrations.py

API endpoints for managing email integrations (Gmail, Outlook).
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.api.v1.email import get_current_user_id
from app.api.v1.activity import log_activity, ActivityType
from app.services.postgres_client import postgres_client
from app.auth.graph_auth import DelegatedGraphAuthenticator

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/integrations",
    tags=["Integrations"],
)

# Enums and Models
class IntegrationType(str, Enum):
    GMAIL = "gmail"
    OUTLOOK = "outlook"

class IntegrationStatus(BaseModel):
    type: IntegrationType
    connected: bool
    email: Optional[str] = None
    connected_at: Optional[datetime] = None
    last_sync: Optional[datetime] = None

class IntegrationResponse(BaseModel):
    integrations: List[IntegrationStatus]

# API Endpoints
@router.get("", response_model=IntegrationResponse)
async def get_integration_status(
    current_user_id: str = Depends(get_current_user_id),
) -> IntegrationResponse:
    """
    Get status of all email integrations for the current user.
    """
    try:
        # Check Outlook/Microsoft integration
        outlook_token = await postgres_client.fetch_one(
            """
            SELECT user_email, created_at, last_seen_timestamp
            FROM auth_tokens
            WHERE user_id = $1
            """,
            current_user_id
        )
        
        outlook_status = IntegrationStatus(
            type=IntegrationType.OUTLOOK,
            connected=bool(outlook_token),
            email=outlook_token["user_email"] if outlook_token else None,
            connected_at=outlook_token["created_at"] if outlook_token else None,
            last_sync=outlook_token["last_seen_timestamp"] if outlook_token else None,
        )
        
        # Gmail integration - check if we have stored OAuth tokens
        gmail_token = await postgres_client.fetch_one(
            """
            SELECT email, created_at, last_sync
            FROM gmail_tokens
            WHERE user_id = $1
            """,
            current_user_id
        )
        
        gmail_status = IntegrationStatus(
            type=IntegrationType.GMAIL,
            connected=bool(gmail_token),
            email=gmail_token["email"] if gmail_token else None,
            connected_at=gmail_token["created_at"] if gmail_token else None,
            last_sync=gmail_token["last_sync"] if gmail_token else None,
        )
        
        return IntegrationResponse(integrations=[outlook_status, gmail_status])
        
    except Exception as e:
        logger.error(f"Failed to get integration status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get integration status")

@router.post("/gmail/connect")
async def connect_gmail(
    current_user_id: str = Depends(get_current_user_id),
) -> Dict[str, str]:
    """
    Initiate Gmail OAuth connection flow.
    """
    # TODO: Implement Gmail OAuth flow
    # For now, return a placeholder response
    raise HTTPException(
        status_code=501,
        detail="Gmail integration not yet implemented. Currently only Outlook is supported."
    )

@router.post("/gmail/disconnect")
async def disconnect_gmail(
    current_user_id: str = Depends(get_current_user_id),
) -> Dict[str, str]:
    """
    Disconnect Gmail integration.
    """
    try:
        # Delete Gmail tokens
        await postgres_client.execute(
            "DELETE FROM gmail_tokens WHERE user_id = $1",
            current_user_id
        )
        
        # Log activity
        await log_activity(
            user_id=current_user_id,
            activity_type=ActivityType.INTEGRATION_DISCONNECTED,
            title="Gmail Disconnected",
            description="Gmail integration has been disconnected"
        )
        
        return {"message": "Gmail integration disconnected successfully"}
        
    except Exception as e:
        logger.error(f"Failed to disconnect Gmail: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to disconnect Gmail")

@router.post("/outlook/connect")
async def connect_outlook(
    request: Request,
    current_user_id: str = Depends(get_current_user_id),
) -> RedirectResponse:
    """
    Initiate Outlook/Microsoft OAuth connection flow.
    Redirects to Microsoft login page.
    """
    try:
        # Reuse existing auth flow from auth_router
        auth_client = DelegatedGraphAuthenticator(http_client=request.app.state.http_client)
        auth_url = auth_client.get_auth_flow_url()
        
        # Store user_id in session/state for callback
        # Note: In production, use proper session management
        
        return RedirectResponse(url=auth_url)
        
    except Exception as e:
        logger.error(f"Failed to initiate Outlook connection: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to initiate Outlook connection")

@router.post("/outlook/disconnect")
async def disconnect_outlook(
    current_user_id: str = Depends(get_current_user_id),
) -> Dict[str, str]:
    """
    Disconnect Outlook integration by removing stored tokens.
    """
    try:
        # Delete auth tokens
        result = await postgres_client.execute(
            "DELETE FROM auth_tokens WHERE user_id = $1",
            current_user_id
        )
        
        # Log activity
        await log_activity(
            user_id=current_user_id,
            activity_type=ActivityType.INTEGRATION_DISCONNECTED,
            title="Outlook Disconnected",
            description="Outlook integration has been disconnected"
        )
        
        return {"message": "Outlook integration disconnected successfully"}
        
    except Exception as e:
        logger.error(f"Failed to disconnect Outlook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to disconnect Outlook")
