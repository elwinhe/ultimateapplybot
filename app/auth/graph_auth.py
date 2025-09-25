"""
app/auth/graph_auth.py

Handles the multi-user delegated authentication flow.
"""
import logging
import secrets
import httpx
from typing import Optional
from jose import jwt, JWTError

from app.config import settings
from app.services.postgres_client import store_refresh_token, get_refresh_token

logger = logging.getLogger(__name__)

class GraphAuthError(Exception): pass
class GraphAuthTokenError(GraphAuthError): pass

class DelegatedGraphAuthenticator:
    _http_client: httpx.AsyncClient
    _token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    _auth_url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None):
        self._http_client = http_client or httpx.AsyncClient()

    def get_auth_flow_url(self, user_id: Optional[str] = None) -> str:
        """Builds the URL for any user to sign in."""
        # Generate a secure random nonce for CSRF protection
        nonce = secrets.token_urlsafe(32)
        
        # Include user_id in state parameter for callback association
        state = f"{nonce}"
        if user_id:
            state = f"{nonce}:{user_id}"
            logger.info("Generated OAuth URL with user_id %s in state parameter", user_id)
        
        params = {
            "client_id": settings.CLIENT_ID,
            "response_type": "code id_token",
            "redirect_uri": settings.REDIRECT_URI,
            "scope": "openid profile email Mail.Read offline_access",
            "response_mode": "form_post",
            "state": state,
            "nonce": nonce
        }
        request = httpx.Request("GET", self._auth_url, params=params)
        return str(request.url)

    async def acquire_and_store_tokens(self, code: str, id_token: str, state: Optional[str] = None, app_user_id: Optional[str] = None) -> None:
        """Acquires tokens and stores the refresh token against the user's ID."""
        # Input validation
        if not code or len(code) < 10:
            raise GraphAuthTokenError("Invalid authorization code format")
        if not id_token or len(id_token) < 10:
            raise GraphAuthTokenError("Invalid id_token format")
            
        # Extract session key from state parameter and resolve to actual user_id
        extracted_session_key = None
        resolved_user_id = None
        
        if state and ":" in state:
            _, extracted_session_key = state.split(":", 1)
            logger.info("Extracted session key %s from OAuth state parameter", extracted_session_key)
            
            # Resolve session key to actual user_id using Redis
            try:
                import redis
                redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
                resolved_user_id = redis_client.get(f"oauth_session:{extracted_session_key}")
                if resolved_user_id:
                    logger.info("Resolved session key %s to user_id %s", extracted_session_key, resolved_user_id)
                    # Clean up the session key
                    redis_client.delete(f"oauth_session:{extracted_session_key}")
                else:
                    logger.warning("Failed to resolve session key %s - may have expired", extracted_session_key)
            except Exception as e:
                logger.error("Failed to resolve OAuth session key: %s", e)
            
        # Determine which user_id to use - prioritize resolved from session, then passed parameter
        final_app_user_id = resolved_user_id or app_user_id
        logger.info("Using final_app_user_id: %s (resolved: %s, passed: %s)", final_app_user_id, resolved_user_id, app_user_id)
        
        # Get Microsoft user info for email address
        try:
            claims = jwt.get_unverified_claims(id_token)
            microsoft_user_email = claims.get("preferred_username") or claims.get("email")
            microsoft_user_id = claims.get("oid")
            if not microsoft_user_email:
                raise GraphAuthTokenError("User email not found in id_token.")
        except JWTError as e:
            raise GraphAuthTokenError("Invalid id_token.") from e

        # We must have an application user_id to proceed
        if not final_app_user_id:
            raise GraphAuthTokenError("No application user ID available. User must be logged in to connect accounts.")

        token_data = {
            "grant_type": "authorization_code",
            "client_id": settings.CLIENT_ID,
            "client_secret": settings.CLIENT_SECRET,
            "scope": "Mail.Read offline_access",
            "code": code,
            "redirect_uri": settings.REDIRECT_URI,
        }
        
        response = await self._http_client.post(self._token_url, data=token_data)
        if response.status_code != 200:
            raise GraphAuthTokenError(f"Failed to exchange code for token: {response.text}")

        result = response.json()
        refresh_token = result.get("refresh_token")
        access_token = result.get("access_token")
        if not refresh_token:
            raise GraphAuthTokenError("No refresh token returned.")

        # Always use the application user_id (never fall back to Microsoft ID)
        await store_refresh_token(final_app_user_id, refresh_token, microsoft_user_email, access_token)
        logger.info("Successfully stored refresh token for app_user %s with Microsoft email %s", final_app_user_id, microsoft_user_email)

    async def get_access_token_for_user(self, user_id: str) -> str:
        """Gets a new access token for a specific user."""
        # Input validation
        if not user_id or not isinstance(user_id, str):
            raise GraphAuthError("Invalid user_id provided")
            
        refresh_token = await get_refresh_token(user_id)
        if not refresh_token:
            raise GraphAuthError(f"No refresh token found for user {user_id}.")

        token_data = {
            "grant_type": "refresh_token",
            "client_id": settings.CLIENT_ID,
            "client_secret": settings.CLIENT_SECRET,
            "refresh_token": refresh_token,
        }
        
        response = await self._http_client.post(self._token_url, data=token_data)
        if response.status_code != 200:
            raise GraphAuthTokenError(f"Failed to refresh token for user {user_id}: {response.text}")

        result = response.json()
        if new_refresh_token := result.get("refresh_token"):
            await store_refresh_token(user_id, new_refresh_token)

        return result["access_token"]