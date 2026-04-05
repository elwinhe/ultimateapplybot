"""
app/api/v1/integrations.py

API endpoints for managing email integrations (Gmail, Outlook).
"""
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Request
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

class ConnectedAccount(BaseModel):
    id: str
    email: str
    microsoft_user_id: Optional[str] = None
    connected_at: datetime
    last_authenticated: Optional[datetime] = None
    expires_at: Optional[datetime] = None

class IntegrationStatus(BaseModel):
    type: IntegrationType
    connected: bool
    email: Optional[str] = None  # For backward compatibility
    connected_at: Optional[datetime] = None  # For backward compatibility
    last_sync: Optional[datetime] = None  # For backward compatibility
    accounts: Optional[List[ConnectedAccount]] = None  # New field for multiple accounts

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
        # Check Outlook/Microsoft integrations - get all connected accounts
        outlook_tokens = await postgres_client.fetch_all(
            """
            SELECT user_email, created_at, last_seen_timestamp, provider, expires_at, id
            FROM auth_tokens
            WHERE user_id = $1 AND provider = 'microsoft'
            """,
            current_user_id
        )
        
        # Convert tokens to ConnectedAccount objects
        outlook_accounts = []
        for token in outlook_tokens:
            if token["user_email"]:  # Only include accounts with email addresses
                account = ConnectedAccount(
                    id=str(token["id"]),
                    email=token["user_email"],
                    microsoft_user_id=None,  # No longer storing Microsoft user ID
                    connected_at=token["created_at"],
                    last_authenticated=token["last_seen_timestamp"],
                    expires_at=token["expires_at"]
                )
                outlook_accounts.append(account)
        
        # Create status object with all connected accounts
        outlook_status = IntegrationStatus(
            type=IntegrationType.OUTLOOK,
            connected=bool(outlook_accounts),
            email=outlook_accounts[0].email if outlook_accounts else None,  # For backward compatibility
            connected_at=outlook_accounts[0].connected_at if outlook_accounts else None,  # For backward compatibility
            last_sync=outlook_accounts[0].last_authenticated if outlook_accounts else None,  # For backward compatibility
            accounts=outlook_accounts if outlook_accounts else None
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
) -> Dict[str, str]:
    """
    Initiate Outlook/Microsoft OAuth connection flow.
    Returns the OAuth URL for the frontend to redirect to.
    """
    try:
        # Generate a unique session key for this OAuth attempt
        import secrets
        import redis
        from app.config import settings as app_settings
        
        oauth_session_key = secrets.token_urlsafe(32)
        
        # Store the user_id in Redis with the session key (no expiration)
        redis_client = redis.Redis.from_url(app_settings.REDIS_URL, decode_responses=True)
        redis_client.set(f"oauth_session:{oauth_session_key}", current_user_id)
        
        # Use the session key instead of user_id in the OAuth state
        auth_client = DelegatedGraphAuthenticator(http_client=request.app.state.http_client)
        auth_url = auth_client.get_auth_flow_url(user_id=oauth_session_key)
        
        logger.info("Created OAuth session %s for user %s", oauth_session_key, current_user_id)
        
        return {"redirectUrl": auth_url}
        
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

@router.get("/outlook/details")
async def get_outlook_details(
    current_user_id: str = Depends(get_current_user_id),
) -> Dict[str, Any]:
    """
    Get detailed information about the Outlook integration for the current user.
    """
    try:
        # Get detailed Outlook/Microsoft integration info
        outlook_details = await postgres_client.fetch_one(
            """
            SELECT 
                user_id,
                user_email,
                provider,
                expires_at,
                scope,
                created_at,
                updated_at,
                last_seen_timestamp
            FROM auth_tokens
            WHERE user_id = $1 AND provider = 'microsoft'
            """,
            current_user_id
        )
        
        if not outlook_details:
            return {
                "connected": False,
                "message": "No Outlook integration found for this user"
            }
        
        return {
            "connected": True,
            "user_id": str(outlook_details["user_id"]),
            "user_email": outlook_details["user_email"],
            "provider": outlook_details["provider"],
            "expires_at": outlook_details["expires_at"].isoformat() if outlook_details["expires_at"] else None,
            "scope": outlook_details["scope"],
            "connected_at": outlook_details["created_at"].isoformat() if outlook_details["created_at"] else None,
            "last_updated": outlook_details["updated_at"].isoformat() if outlook_details["updated_at"] else None,
            "last_sync": outlook_details["last_seen_timestamp"].isoformat() if outlook_details["last_seen_timestamp"] else None,
        }
        
    except Exception as e:
        logger.error(f"Failed to get Outlook details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get Outlook details")
