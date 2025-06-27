"""
app/services/graph_client.py

Service layer for interacting with the Microsoft Graph API.
"""
from __future__ import annotations

import logging
from typing import Iterable, List, Optional, Dict
from datetime import datetime, timezone

import httpx

# --- Qualified Internal Imports ---
from app.auth.graph_auth import DelegatedGraphAuthenticator, GraphAuthError
from app.config import settings
from app.models.email import Email

logger = logging.getLogger(__name__)

# --- Custom Typed Exceptions ---
class GraphClientError(Exception):
    """Base exception for GraphClient failures."""
    pass

class GraphAPIFailedRequest(GraphClientError):
    """Raised when the Microsoft Graph API returns an error status code."""
    pass

class GraphClientAuthenticationError(GraphClientError):
    """Raised when authentication fails."""
    pass


_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


class GraphClient:
    """
    A high-level async client for Microsoft Graph email operations.

    This client is designed for testability and robustness, using an injected
    HTTP client. It supports delegated authentication flow.
    """
    _http_client: httpx.AsyncClient
    _authenticator: DelegatedGraphAuthenticator

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        """
        Initializes the GraphClient with an HTTP client.

        Args:
            http_client: An httpx.AsyncClient for making requests. Reusing the
                         client improves performance.
        """
        self._http_client = http_client
        self._authenticator = DelegatedGraphAuthenticator(http_client=http_client)
        logger.info("GraphClient initialized for delegated authentication")

    async def _get_auth_headers(self) -> Dict[str, str]:
        """
        Asynchronously acquires a token and formats it into authorization headers.
        
        Returns:
            Dictionary containing Authorization header with Bearer token.
            
        Raises:
            GraphClientAuthenticationError: If authentication fails.
        """
        logger.debug("Acquiring access token for Graph API call...")
        try:
            token = await self._authenticator.get_access_token_for_user()
            return {"Authorization": f"Bearer {token}"}
        except GraphAuthError as e:
            logger.error("Authentication failed while preparing Graph API request: %s", str(e))
            raise GraphClientAuthenticationError("Could not authenticate for Graph API request") from e

    async def fetch_messages(
        self,
        *,
        top: int = 50,
        since: Optional[datetime] = None,
        select: Optional[Iterable[str]] = None,
    ) -> List[Email]:
        """
        Fetches a list of email messages from the authenticated user's mailbox.

        Args:
            top: The maximum number of messages to return (default: 50).
            since: If provided, fetches messages received after this timestamp.
            select: A list of specific fields to retrieve.

        Returns:
            A list of validated Pydantic Email models.

        Raises:
            GraphAPIFailedRequest: If the API returns a non-2xx status code.
            GraphClientError: For other unexpected errors during the process.
        """
        params: dict[str, str | int] = {
            "$top": top,
            "$orderby": "receivedDateTime DESC",
        }
        if since:
            iso = since.astimezone(timezone.utc).isoformat(timespec="seconds")
            params["$filter"] = f"receivedDateTime gt {iso}"
        if select:
            params["$select"] = ",".join(select)

        # Use /me endpoint for delegated auth
        url = f"{_GRAPH_BASE_URL}/me/messages"
        logger.info("Fetching messages from authenticated user's mailbox with params: %s", params)

        try:
            headers = await self._get_auth_headers()
            response = await self._http_client.get(url, headers=headers, params=params)
            response.raise_for_status()
            raw_list = response.json().get("value", [])

            logger.info("Successfully fetched %d messages from Graph API", len(raw_list))
            return [Email.model_validate(m) for m in raw_list]

        except httpx.HTTPStatusError as e:
            logger.error("HTTP error fetching messages: %s - %s", e.response.status_code, e.response.text)
            raise GraphAPIFailedRequest(f"Graph API returned status {e.response.status_code}") from e
        except GraphClientAuthenticationError:
            # Re-raise authentication errors as-is
            raise
        except Exception as e:
            logger.error("Unexpected error fetching messages: %s", str(e), exc_info=True)
            raise GraphClientError("An unexpected error occurred during message fetching") from e

    async def fetch_eml_content(self, *, message_id: str) -> bytes:
        """
        Fetches the raw MIME content (.eml) of a single email message.

        Args:
            message_id: The unique identifier of the message.

        Returns:
            The raw MIME content as bytes.

        Raises:
            GraphAPIFailedRequest: If the API returns a non-2xx status code.
            GraphClientError: For other unexpected errors during the process.
        """
        url = f"{_GRAPH_BASE_URL}/me/messages/{message_id}/$value"
        logger.info("Fetching EML content from: %s", url)

        try:
            headers = await self._get_auth_headers()
            response = await self._http_client.get(url, headers=headers)
            response.raise_for_status()
            return response.content
        except httpx.HTTPStatusError as e:
            logger.error("HTTP error fetching EML content: %s - %s", e.response.status_code, e.response.text)
            raise GraphAPIFailedRequest(f"Graph API returned status {e.response.status_code}") from e
        except GraphClientAuthenticationError:
            # Re-raise authentication errors as-is
            raise
        except Exception as e:
            logger.error("Unexpected error fetching EML content: %s", str(e), exc_info=True)
            raise GraphClientError("An unexpected error occurred during EML content fetching") from e