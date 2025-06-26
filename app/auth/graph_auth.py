"""
app/auth/graph_auth.py

Handles OAuth 2.0 Authorization Code Flow for Microsoft Graph API.
"""
import logging
from typing import Optional
import redis
from msal import ConfidentialClientApplication

from app.config import settings

logger = logging.getLogger(__name__)

# Define a Redis key for storing the user's refresh token
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
    """Manages the delegated authentication flow."""

    def __init__(self, redis_url: Optional[str] = None) -> None:
        """
        Initialize the authenticator.
        
        Args:
            redis_url: Optional Redis URL override for testing
        """
        if not settings.CLIENT_ID:
            raise GraphAuthValidationError("CLIENT_ID is required")
        if not settings.CLIENT_SECRET:
            raise GraphAuthValidationError("CLIENT_SECRET is required for ConfidentialClientApplication")
        if not settings.REDIRECT_URI:
            raise GraphAuthValidationError("REDIRECT_URI is required")
        if not settings.TARGET_EXTERNAL_USER:
            raise GraphAuthValidationError("TARGET_EXTERNAL_USER is required")
        
        # Use 'common' authority to support both work/school and personal accounts
        authority = "https://login.microsoftonline.com/common"
        
        try:
            self._app = ConfidentialClientApplication(
                settings.CLIENT_ID,
                authority=authority,
                client_credential=settings.CLIENT_SECRET,
            )
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
            auth_url = self._app.get_authorization_request_url(
                scopes=["Mail.Read", "offline_access"],
                redirect_uri=settings.REDIRECT_URI
            )
            logger.debug("Generated auth flow URL", extra={"redirect_uri": settings.REDIRECT_URI})
            return auth_url
        except Exception as e:
            logger.error("Failed to generate auth flow URL", extra={"error": str(e)})
            raise GraphAuthError("Failed to generate authentication URL") from e

    def acquire_token_by_auth_code(self, auth_code: str) -> None:
        """
        Acquires tokens using an authorization code and securely stores the refresh token.
        
        Args:
            auth_code: The authorization code from Microsoft
            
        Raises:
            GraphAuthValidationError: If auth_code is invalid
            GraphAuthTokenError: If token acquisition fails
            GraphAuthError: For other authentication errors
        """
        if not auth_code or len(auth_code) < 10:
            raise GraphAuthValidationError("Invalid authorization code format")
        
        try:
            result = self._app.acquire_token_by_authorization_code(
                auth_code,
                scopes=["Mail.Read", "offline_access"],
                redirect_uri=settings.REDIRECT_URI
            )
            
            if "error" in result:
                logger.error("Token acquisition failed", extra={"error": result.get("error")})
                raise GraphAuthTokenError(result.get("error_description", "Unknown token error"))
            
            refresh_token = result.get("refresh_token")
            if not refresh_token:
                raise GraphAuthTokenError("No refresh token returned. Ensure 'offline_access' scope is granted.")

            # Store the refresh token in Redis
            self._redis_client.set(REFRESH_TOKEN_KEY, refresh_token)
            logger.info(
                "Successfully acquired and stored refresh token", 
                extra={"user": settings.TARGET_EXTERNAL_USER}
            )
            
        except (GraphAuthValidationError, GraphAuthTokenError):
            # Re-raise our specific exceptions
            raise
        except Exception as e:
            logger.error("Unexpected error during token acquisition", extra={"error": str(e)})
            raise GraphAuthError("Failed to acquire authentication tokens") from e

    async def get_access_token_for_user(self) -> str:
        """
        Acquires a new access token using a stored refresh token.
        This is the method the background task will call.
        
        Returns:
            The access token for Microsoft Graph API
            
        Raises:
            GraphAuthTokenError: If no refresh token is found or refresh fails
            GraphAuthError: For other authentication errors
        """
        try:
            refresh_token = self._redis_client.get(REFRESH_TOKEN_KEY)
            if not refresh_token:
                raise GraphAuthTokenError(
                    f"No refresh token found for user {settings.TARGET_EXTERNAL_USER}. "
                    "Please re-authenticate via /api/v1/auth/login."
                )

            result = self._app.acquire_token_by_refresh_token(
                refresh_token,
                scopes=["Mail.Read"]
            )
            
            if "access_token" not in result:
                logger.error("Token refresh failed", extra={"error": result.get("error")})
                raise GraphAuthTokenError(result.get("error_description", "Unknown refresh error"))
                
            # If a new refresh token is issued, update it in storage
            if "refresh_token" in result:
                self._redis_client.set(REFRESH_TOKEN_KEY, result["refresh_token"])
                logger.info("Updated refresh token in storage")
            
            logger.debug("Successfully acquired access token")
            return result["access_token"]
            
        except (GraphAuthTokenError, GraphAuthError):
            # Re-raise our specific exceptions
            raise
        except Exception as e:
            logger.error("Unexpected error during token refresh", extra={"error": str(e)})
            raise GraphAuthError("Failed to refresh access token") from e