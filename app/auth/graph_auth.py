"""
app/auth/graph_auth.py

Authentication for the Microsoft Graph API.
"""

import logging
from typing import Optional
from msal import ConfidentialClientApplication
from app.config import settings

logger = logging.getLogger(__name__)

class GraphAuthError(Exception):
    """Raised when authentication fails."""
    pass

# A class based approach is more maintainable and efficient
class GraphAuthenticator:
    """
    Handles authentication with Microsoft Graph API.
    Uses MSAL to acquire tokens for the Graph API.
    Caches tokens in memory for efficiency.
    Raises GraphAuthError on authentication failure.
    """
    _app: ConfidentialClientApplication

    def __init__(self) -> None:
        """
        Initializes the ConfidentialClientApplication instance.
        """
        authority = f"https://login.microsoftonline.com/{settings.TENANT_ID}"
        self._app = ConfidentialClientApplication(
            settings.CLIENT_ID,
            authority=authority,
            client_credential=settings.CLIENT_SECRET,
        )

    def get_access_token(self) -> str:
        """
        Acquires an access token for the Graph API using the client credentials flow.

        Returns:
            A valid access token as a string.

        Raises:
            GraphAuthError: If the token acquisition fails for any reason.
        """
        scopes: list[str] = ["https://graph.microsoft.com/.default"]

        # MSAL caches tokens in memory.
        result: Optional[dict] = self._app.acquire_token_silent(scopes, account=None)

        if not result:
            logger.info("No cached token found. Acquiring a new token from AAD.")
            result = self._app.acquire_token_for_client(scopes=scopes)

        # Check for the 'error' key specifically, which is what MSAL returns on failure.
        if "access_token" not in result:
            error_summary = result.get("error_description", "No error description provided.")
            logger.critical(
                "Failed to acquire Graph API access token. Error: %s, Details: %s",
                result.get("error"),
                error_summary
            )
            raise GraphAuthError(
                f"Could not acquire token: {result.get('error')} - {error_summary}"
            )

        return result["access_token"]

# Create a single instance that can be imported and used throughout the application.
# This ensures the authenticator is initialized only once.
graph_authenticator = GraphAuthenticator()
