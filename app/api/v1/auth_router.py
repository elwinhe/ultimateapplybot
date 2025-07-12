"""
app/api/v1/auth_router.py

API router for handling the user-facing authentication flow.
"""
import logging
from typing import Annotated

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
) -> RedirectResponse:
    """
    Redirects the user to the Microsoft login page to grant consent.
    This is the first step of the OAuth 2.0 flow.
    """
    try:
        auth_url = auth_client.get_auth_flow_url()
        logger.info("Redirecting user to Microsoft for authentication.")
        return RedirectResponse(url=auth_url)
    except Exception as e:
        logger.error("Failed to generate auth URL", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to initiate authentication.")


@router.post(
    "/callback",
    summary="Handle Microsoft authentication callback",
    response_model=AuthResponse,
)
async def auth_callback(
    code: Annotated[str, Form()],
    id_token: Annotated[str, Form()],
    auth_client: Annotated[DelegatedGraphAuthenticator, Depends(get_auth_client)],
) -> AuthResponse:
    """
    Handles the form_post callback from Microsoft after user authentication.
    Exchanges the authorization code for tokens and stores them for the user.
    """
    try:
        await auth_client.acquire_and_store_tokens(code, id_token)
        return AuthResponse(message="Authentication successful. Refresh token stored.")
    except GraphAuthError as e:
        logger.error("Failed to acquire tokens during callback", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Authentication failed: {e}")
