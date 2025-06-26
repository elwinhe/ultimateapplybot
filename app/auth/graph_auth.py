"""
app/auth/graph_auth.py

Handles OAuth 2.0 Authorization Code Flow for Microsoft Graph API.
"""
import logging
import redis
from typing import Dict
from msal import ConfidentialClientApplication

from app.config import settings

logger = logging.getLogger(__name__)

# Define a Redis key for storing the user's refresh token
REFRESH_TOKEN_KEY = f"user_refresh_token:{settings.TARGET_EXTERNAL_USER}"

class GraphAuthError(Exception):
    pass

class DelegatedGraphAuthenticator:
    """Manages the delegated authentication flow."""

    def __init__(self) -> None:
        # --- THE FIX ---
        # To allow personal accounts, the authority URL must use 'common'
        # instead of a specific tenant ID.
        authority = "https://login.microsoftonline.com/common"
        self._app = ConfidentialClientApplication(
            settings.CLIENT_ID,
            authority=authority,
            client_credential=settings.CLIENT_SECRET,
        )
        self._redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

    def get_auth_flow_url(self) -> str:
        """Builds the URL to which the user must be redirected to sign in."""
        return self._app.get_authorization_request_url(
            scopes=["Mail.Read", "offline_access"],
            redirect_uri=settings.REDIRECT_URI
        )

    def acquire_token_by_auth_code(self, auth_code: str) -> None:
        """
        Acquires tokens using an authorization code and securely stores the refresh token.
        """
        result = self._app.acquire_token_by_authorization_code(
            auth_code,
            scopes=["Mail.Read", "offline_access"],
            redirect_uri=settings.REDIRECT_URI
        )
        if "error" in result:
            logger.error("Failed to acquire token by auth code: %s", result)
            raise GraphAuthError(result.get("error_description"))
        
        refresh_token = result.get("refresh_token")
        if not refresh_token:
            raise GraphAuthError("No refresh token was returned. Ensure 'offline_access' scope is granted.")

        # Securely store the refresh token (e.g., in Redis)
        self._redis_client.set(REFRESH_TOKEN_KEY, refresh_token)
        logger.info("Successfully acquired and stored refresh token for user: %s", settings.TARGET_EXTERNAL_USER)

    async def get_access_token_for_user(self) -> str:
        """
        Acquires a new access token using a stored refresh token.
        This is the method the background task will call.
        """
        refresh_token = self._redis_client.get(REFRESH_TOKEN_KEY)
        if not refresh_token:
            raise GraphAuthError(f"No refresh token found for user. Please re-authenticate via /api/v1/auth/login.")

        result = self._app.acquire_token_by_refresh_token(
            refresh_token,
            scopes=["Mail.Read"]
        )
        if "access_token" not in result:
            logger.error("Failed to acquire token by refresh token: %s", result)
            raise GraphAuthError(result.get("error_description"))
            
        # If a new refresh token is issued, update it in storage
        if "refresh_token" in result:
            self._redis_client.set(REFRESH_TOKEN_KEY, result["refresh_token"])
            logger.info("Received and stored an updated refresh token.")

        return result["access_token"]

# Singleton instance
delegated_auth_client = DelegatedGraphAuthenticator()