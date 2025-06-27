"""
app/auth/graph_auth.py

Provides a robust, fully asynchronous authentication client for the Microsoft
Graph API using httpx for non-blocking token acquisition.
"""
import logging
import redis
import httpx
from typing import Optional

from app.config import settings
from app.services.postgres_client import store_refresh_token, get_refresh_token

logger = logging.getLogger(__name__)

# Redis key for storing refresh tokens
REFRESH_TOKEN_KEY = f"user_refresh_token:{settings.TARGET_EXTERNAL_USER}"


class GraphAuthError(Exception):
    """Raised when authentication operations fail."""
    pass


class GraphAuthValidationError(GraphAuthError):
    """Raised when authentication input validation fails."""
    pass


class GraphAuthTokenError(GraphAuthError):
    """Raised when token acquisition or refresh fails."""
    pass


class DelegatedGraphAuthenticator:
    """Manages the delegated authentication flow with full async support."""

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None, redis_url: Optional[str] = None) -> None:
        """
        Initialize the authenticator.
        
        Args:
            http_client: Optional httpx.AsyncClient for dependency injection
            redis_url: Optional Redis URL override for testing
        """
        if not settings.CLIENT_ID:
            raise GraphAuthValidationError("CLIENT_ID is required")
        if not settings.REDIRECT_URI:
            raise GraphAuthValidationError("REDIRECT_URI is required")
        if not settings.TARGET_EXTERNAL_USER:
            raise GraphAuthValidationError("TARGET_EXTERNAL_USER is required")
        
        # Store the HTTP client for async operations
        self._http_client = http_client
        self._token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
        self._auth_url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
        
        # Check if we're using a public client (no client secret) or confidential client
        self._is_public_client = not settings.CLIENT_SECRET
        
        try:
            self._redis_client = redis.Redis.from_url(
                redis_url or settings.REDIS_URL, 
                decode_responses=True
            )
            logger.info("DelegatedGraphAuthenticator initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize DelegatedGraphAuthenticator", extra={"error": str(e)})
            raise GraphAuthError("Failed to initialize authentication client") from e

    def get_auth_flow_url(self) -> str:
        """
        Builds the URL to which the user must be redirected to sign in.
        
        Returns:
            The Microsoft OAuth authorization URL
            
        Raises:
            GraphAuthError: If URL generation fails
        """
        try:
            params = {
                "client_id": settings.CLIENT_ID,
                "response_type": "code",
                "redirect_uri": settings.REDIRECT_URI,
                "scope": "Mail.Read offline_access",
                "response_mode": "query"
            }
            request = httpx.Request("GET", self._auth_url, params=params)
            auth_url = str(request.url)
            logger.debug("Generated auth flow URL", extra={"redirect_uri": settings.REDIRECT_URI})
            return auth_url
        except Exception as e:
            logger.error("Failed to generate auth flow URL", extra={"error": str(e)})
            raise GraphAuthError("Failed to generate authentication URL") from e

    async def acquire_token_by_auth_code(self, auth_code: str) -> None:
        """
        Asynchronously acquires tokens using an authorization code and securely stores the refresh token.
        
        Args:
            auth_code: The authorization code from Microsoft
            
        Raises:
            GraphAuthValidationError: If auth_code is invalid
            GraphAuthTokenError: If token acquisition fails
            GraphAuthError: For other authentication errors
        """
        if not auth_code or len(auth_code) < 10:
            raise GraphAuthValidationError("Invalid authorization code format")
        
        if not self._http_client:
            raise GraphAuthError("HTTP client not available for async token acquisition")
        
        token_data = {
            "grant_type": "authorization_code",
            "client_id": settings.CLIENT_ID,
            "scope": "Mail.Read offline_access",
            "code": auth_code,
            "redirect_uri": settings.REDIRECT_URI,
        }
        
        # Only include client_secret for confidential clients
        if not self._is_public_client and settings.CLIENT_SECRET:
            token_data["client_secret"] = settings.CLIENT_SECRET
        
        try:
            logger.debug("Exchanging auth code for token", extra={"is_public_client": self._is_public_client})
            response = await self._http_client.post(self._token_url, data=token_data)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.error("HTTP error exchanging auth code for token: %s", e.response.text, exc_info=True)
                raise GraphAuthTokenError(f"Failed to exchange authorization code for token: {e.response.text}") from e
            
            result = response.json()
            logger.debug("Token response received", extra={"response_keys": list(result.keys())})
            
            if "error" in result:
                logger.error("Token acquisition failed", extra={"error": result.get("error"), "error_description": result.get("error_description")})
                raise GraphAuthTokenError(result.get("error_description", "Unknown token error"))
            
            refresh_token = result.get("refresh_token")
            if not refresh_token:
                logger.error("No refresh token in response", extra={"response_keys": list(result.keys())})
                raise GraphAuthTokenError("No refresh token returned. Ensure 'offline_access' scope is granted.")

            # Store the refresh token in Postgres
            await store_refresh_token(settings.TARGET_EXTERNAL_USER, refresh_token)
            logger.info(
                "Successfully acquired and stored refresh token", 
                extra={"user": settings.TARGET_EXTERNAL_USER}
            )
            
        except (GraphAuthValidationError, GraphAuthTokenError):
            # Re-raise our specific exceptions
            raise
        except Exception as e:
            logger.error("Unexpected error during token acquisition", extra={"error": str(e), "error_type": type(e).__name__}, exc_info=True)
            raise GraphAuthError("Failed to acquire authentication tokens") from e

    async def get_access_token_for_user(self) -> str:
        """
        Asynchronously acquires a new access token using a stored refresh token.
        This is the method the background task will call.

        Returns:
            The access token for Microsoft Graph API

        Raises:
            GraphAuthTokenError: If no refresh token is found or refresh fails
            GraphAuthError: For other authentication errors
        """
        if not self._http_client:
            raise GraphAuthError("HTTP client not available for async token acquisition")
        
        try:
            refresh_token = await get_refresh_token(settings.TARGET_EXTERNAL_USER)
            if not refresh_token:
                raise GraphAuthTokenError(
                    f"No refresh token found for user {settings.TARGET_EXTERNAL_USER}. "
                    "Please re-authenticate via /api/v1/auth/login."
                )

            token_data = {
                "grant_type": "refresh_token",
                "client_id": settings.CLIENT_ID,
                "scope": "Mail.Read",
                "refresh_token": refresh_token,
            }
            
            # Only include client_secret for confidential clients
            if not self._is_public_client and settings.CLIENT_SECRET:
                token_data["client_secret"] = settings.CLIENT_SECRET
            
            response = await self._http_client.post(self._token_url, data=token_data)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.error("HTTP error refreshing token: %s", e.response.text, exc_info=True)
                raise GraphAuthTokenError(f"Failed to acquire token via refresh token: {e.response.text}") from e
            
            result = response.json()
            
            # Store new refresh token if one is returned (Microsoft may rotate tokens)
            if "refresh_token" in result:
                await store_refresh_token(settings.TARGET_EXTERNAL_USER, result["refresh_token"])
                logger.debug("Stored new refresh token from token refresh")
            
            if "access_token" not in result:
                logger.error("Token refresh failed", extra={"error": result.get("error")})
                raise GraphAuthTokenError(result.get("error_description", "Unknown refresh error"))
                
            logger.debug("Successfully acquired access token")
            return result["access_token"]

        except (GraphAuthTokenError, GraphAuthError):
            # Re-raise our specific exceptions
            raise
        except Exception as e:
            logger.error("Unexpected error during token retrieval", exc_info=True)
            raise GraphAuthError("Failed to refresh access token") from e