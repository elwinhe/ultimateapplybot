"""
app/api/v1/auth_router.py

API router for handling the user-facing authentication flow.
"""
import logging
from fastapi import APIRouter, Query
from fastapi.responses import RedirectResponse, JSONResponse

from app.auth.graph_auth import delegated_auth_client, GraphAuthError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.get("/login", summary="Initiate user authentication")
async def login():
    """
    Redirects the user to the Microsoft login page to grant consent.
    This is the first step of the OAuth 2.0 flow.
    """
    auth_url = delegated_auth_client.get_auth_flow_url()
    logger.info("Redirecting user to Microsoft for authentication.")
    return RedirectResponse(url=auth_url)


@router.get("/callback", summary="Handle Microsoft authentication callback")
async def auth_callback(code: str = Query(...)):
    """
    Handles the callback from Microsoft after user authentication.
    Exchanges the authorization code for tokens and stores them.
    """
    try:
        logger.info("Received authorization code. Acquiring tokens...")
        delegated_auth_client.acquire_token_by_auth_code(code)
        return JSONResponse(
            status_code=200,
            content={"status": "success", "message": "Authentication successful. Refresh token stored."}
        )
    except GraphAuthError as e:
        logger.error("Error during auth callback: %s", str(e), exc_info=True)
        return JSONResponse(
            status_code=400,
            content={"status": "error", "message": str(e)}
        )