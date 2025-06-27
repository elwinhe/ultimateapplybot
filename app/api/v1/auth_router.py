"""
app/api/v1/auth_router.py

API router for handling the user-facing authentication flow.
"""
import logging
from typing import Annotated
from fastapi import APIRouter, Query, HTTPException, Depends
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, HttpUrl
import httpx

from app.auth.graph_auth import DelegatedGraphAuthenticator, GraphAuthError
from app.config import settings
from app.services.postgres_client import store_refresh_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


class AuthResponse(BaseModel):
    """Response model for authentication operations."""
    status: str = Field(..., description="Operation status")
    message: str = Field(..., description="Human-readable message")


class AuthError(BaseModel):
    """Error response model for authentication failures."""
    status: str = Field(default="error", description="Always 'error'")
    message: str = Field(..., description="Error description")
    error_code: str = Field(..., description="Machine-readable error code")


async def get_auth_client() -> DelegatedGraphAuthenticator:
    """Dependency to get the auth client instance."""
    # Create a shared HTTP client for the request
    http_client = httpx.AsyncClient()
    return DelegatedGraphAuthenticator(http_client=http_client)


def validate_auth_code(code: str) -> str:
    """
    Validate the authorization code format.
    
    Args:
        code: The authorization code from Microsoft
        
    Returns:
        The validated code
        
    Raises:
        HTTPException: If the code is invalid
    """
    if not code or len(code) < 10:
        raise HTTPException(
            status_code=400, 
            detail="Invalid authorization code format"
        )
    return code


async def process_auth_code(
    code: str, 
    auth_client: DelegatedGraphAuthenticator
) -> AuthResponse:
    """
    Process the authorization code and acquire tokens.
    
    Args:
        code: Validated authorization code
        auth_client: Injected auth client
        
    Returns:
        AuthResponse with success status
        
    Raises:
        HTTPException: If token acquisition fails
    """
    try:
        await auth_client.acquire_token_by_auth_code(code)
        logger.info("Successfully processed authorization code")
        return AuthResponse(
            status="success",
            message="Authentication successful. Refresh token stored."
        )
    except GraphAuthError as e:
        logger.error(
            "Failed to acquire tokens", 
            extra={"error": str(e), "code_length": len(code)}
        )
        raise HTTPException(
            status_code=400,
            detail=f"Authentication failed: {str(e)}"
        ) from e


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
        logger.info("Redirecting user to Microsoft for authentication")
        return RedirectResponse(url=auth_url)
    except Exception as e:
        logger.error("Failed to generate auth URL", extra={"error": str(e)})
        raise HTTPException(
            status_code=500,
            detail="Failed to initiate authentication"
        ) from e


@router.get(
    "/callback", 
    summary="Handle Microsoft authentication callback",
    response_model=AuthResponse,
    responses={
        400: {"model": AuthError},
        500: {"model": AuthError}
    }
)
async def auth_callback(
    code: Annotated[str, Query(..., description="Authorization code from Microsoft")],
    auth_client: Annotated[DelegatedGraphAuthenticator, Depends(get_auth_client)]
) -> AuthResponse:
    """
    Handles the callback from Microsoft after user authentication.
    Exchanges the authorization code for tokens and stores them.
    """
    # Validate input
    validated_code = validate_auth_code(code)
    
    # Process the auth code (pure function)
    return await process_auth_code(validated_code, auth_client)