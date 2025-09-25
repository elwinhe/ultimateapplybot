"""
app/api/v1/auth_router.py

API router for handling the user-facing authentication flow.
"""
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.auth.graph_auth import DelegatedGraphAuthenticator, GraphAuthError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


# Pydantic Response Models 
class AuthResponse(BaseModel):
    """Response model for successful authentication."""
    status: str = Field(default="success")
    message: str


# Dependency Injection 
def get_auth_client(request: Request) -> DelegatedGraphAuthenticator:
    """
    Dependency provider for the DelegatedGraphAuthenticator.
    It correctly retrieves the shared httpx.AsyncClient from the app state.
    """
    try:
        # Use the shared HTTP client managed by the application's lifespan
        http_client = request.app.state.http_client
        return DelegatedGraphAuthenticator(http_client=http_client)
    except AttributeError:
        logger.critical("httpx.AsyncClient not found in app state. Is the lifespan manager configured?")
        raise HTTPException(status_code=500, detail="Server is not configured correctly.")


# API Endpoints 
@router.get("/login", summary="Initiate user authentication")
async def login(
    auth_client: Annotated[DelegatedGraphAuthenticator, Depends(get_auth_client)]
) -> dict:
    """
    Returns the Microsoft login URL for the frontend to redirect to.
    This is the first step of the OAuth 2.0 flow.
    """
    try:
        auth_url = auth_client.get_auth_flow_url()
        logger.info("Generated Microsoft authentication URL.")
        return {"redirectUrl": auth_url}
    except Exception as e:
        logger.error("Failed to generate auth URL", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to initiate authentication.")


@router.post(
    "/callback",
    summary="Handle Microsoft authentication callback",
)
async def auth_callback(
    auth_client: Annotated[DelegatedGraphAuthenticator, Depends(get_auth_client)],
    code: Annotated[Optional[str], Form()] = None,
    id_token: Annotated[Optional[str], Form()] = None,
    error: Annotated[Optional[str], Form()] = None,
    error_description: Annotated[Optional[str], Form()] = None,
    state: Annotated[Optional[str], Form()] = None,
) -> RedirectResponse:
    """
    Handles the form_post callback from Microsoft after user authentication.
    Exchanges the authorization code for tokens and stores them for the user.
    Redirects back to the frontend homepage.
    """
    frontend_base_url = "http://localhost:8080"  # Based on terminal output showing port 8080
    
    # Check if user cancelled or there was an error
    if error:
        logger.info(f"Microsoft OAuth cancelled or error: {error} - {error_description}")
        
        if error == "access_denied":
            # User explicitly cancelled
            logger.info("User cancelled Microsoft OAuth, redirecting to homepage")
            return RedirectResponse(url=f"{frontend_base_url}?auth_cancelled=true", status_code=302)
        else:
            # Other OAuth error
            logger.warning(f"Microsoft OAuth error: {error} - {error_description}")
            return RedirectResponse(url=f"{frontend_base_url}?auth_error=oauth_error", status_code=302)
    
    # Check if we have the required parameters for successful auth
    if not code or not id_token:
        logger.warning("Missing required parameters in OAuth callback")
        return RedirectResponse(url=f"{frontend_base_url}?auth_error=missing_parameters", status_code=302)
    
    try:
        await auth_client.acquire_and_store_tokens(code, id_token, state)
        logger.info("Microsoft Outlook authentication successful, redirecting to homepage")
        return RedirectResponse(url=f"{frontend_base_url}?auth_success=outlook_connected", status_code=302)
    except GraphAuthError as e:
        logger.error("Failed to acquire tokens during callback", exc_info=True)
        return RedirectResponse(url=f"{frontend_base_url}?auth_error=outlook_connection_failed", status_code=302)


@router.get("/callback", summary="Handle Microsoft authentication callback (GET)")
async def auth_callback_get(
    request: Request,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    code: Optional[str] = None,
    state: Optional[str] = None,
) -> RedirectResponse:
    """
    Handle GET-based OAuth callback (typically for cancellations or errors).
    """
    frontend_base_url = "http://localhost:8080"
    
    # Check if user cancelled or there was an error
    if error:
        logger.info(f"Microsoft OAuth GET callback - error: {error} - {error_description}")
        
        if error == "access_denied":
            # User explicitly cancelled
            logger.info("User cancelled Microsoft OAuth (GET), redirecting to homepage")
            return RedirectResponse(url=f"{frontend_base_url}?auth_cancelled=true", status_code=302)
        else:
            # Other OAuth error
            logger.warning(f"Microsoft OAuth GET error: {error} - {error_description}")
            return RedirectResponse(url=f"{frontend_base_url}?auth_error=oauth_error", status_code=302)
    
    # If no error but also no code, treat as cancellation
    if not code:
        logger.info("OAuth GET callback without code, treating as cancellation")
        return RedirectResponse(url=f"{frontend_base_url}?auth_cancelled=true", status_code=302)
    
    # If we get here with a code via GET, redirect to main page (unusual case)
    logger.info("OAuth GET callback with code - redirecting to homepage")
    return RedirectResponse(url=frontend_base_url, status_code=302)
