"""
app/services/graph_client.py

Service layer for interacting with the Microsoft Graph API.
"""
from __future__ import annotations
import logging
from typing import Iterable, List, Optional, Dict, AsyncGenerator
from datetime import datetime, timezone
import httpx

from app.auth.graph_auth import DelegatedGraphAuthenticator, GraphAuthError
from app.models.email import Email

logger = logging.getLogger(__name__)

class GraphClientError(Exception): pass
class GraphAPIFailedRequest(GraphClientError): pass
class GraphClientAuthenticationError(GraphClientError): pass

_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

class GraphClient:
    """A high-level async client for Microsoft Graph email operations."""
    _http_client: httpx.AsyncClient
    _authenticator: DelegatedGraphAuthenticator

    def __init__(self, http_client: httpx.AsyncClient) -> None:
        self._http_client = http_client
        self._authenticator = DelegatedGraphAuthenticator(http_client=http_client)
        logger.info("GraphClient initialized for multi-user delegated authentication.")

    async def _get_auth_headers(self, user_id: str) -> Dict[str, str]:
        """Acquires a token for a specific user."""
        # Input validation
        if not user_id or not isinstance(user_id, str):
            raise GraphClientAuthenticationError("Invalid user_id provided")
            
        try:
            logger.debug("Acquiring access token for user: %s", user_id)
            token = await self._authenticator.get_access_token_for_user(user_id)
            return {"Authorization": f"Bearer {token}"}
        except GraphAuthError as e:
            logger.error("Authentication failed for user %s: %s", user_id, str(e))
            raise GraphClientAuthenticationError(f"Could not authenticate for user {user_id}") from e

    async def fetch_messages(
        self, *, user_id: str, top: int = 50, since: Optional[datetime] = None, select: Optional[Iterable[str]] = None
    ) -> List[Email]:
        """
        Fetches all pages of email messages for a specific user, handling pagination.
        """
        if not user_id or not isinstance(user_id, str):
            raise GraphClientError("Invalid user_id provided")
        if not isinstance(top, int) or top < 1 or top > 1000:
            raise GraphClientError("Invalid top parameter: must be between 1 and 1000")
        if since and not isinstance(since, datetime):
            raise GraphClientError("Invalid since parameter: must be a datetime object")
            
        params: dict[str, str | int] = {"$top": top, "$orderby": "receivedDateTime DESC"}
        if since:
            since_str = since.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            params["$filter"] = f"receivedDateTime gt {since_str}"
        if select:
            params["$select"] = ",".join(select)

        all_messages: List[Email] = []
        next_url: Optional[str] = f"{_GRAPH_BASE_URL}/me/messages"
        
        logger.info("Fetching messages for user %s with initial params: %s", user_id, params)
        
        try:
            headers = await self._get_auth_headers(user_id)
            
            while next_url:
                response = await self._http_client.get(
                    next_url, 
                    headers=headers, 
                    params=params if next_url == f"{_GRAPH_BASE_URL}/me/messages" else None,
                )
                response.raise_for_status()
                data = response.json()
                
                raw_messages = data.get("value", [])
                all_messages.extend([Email.model_validate(m) for m in raw_messages])
                
                next_url = data.get("@odata.nextLink")
                if next_url:
                    logger.info("Found nextLink, fetching next page for user %s...", user_id)

            logger.info("Successfully fetched a total of %d messages for user %s", len(all_messages), user_id)
            return all_messages
            
        except httpx.TimeoutException as e:
            logger.error("Timeout fetching messages for user %s: %s", user_id, str(e))
            raise GraphClientError(f"Request timeout for user {user_id}") from e
        except httpx.HTTPStatusError as e:
            logger.error("HTTP error fetching messages for user %s: %s - %s", 
                        user_id, e.response.status_code, e.response.text)
            raise GraphAPIFailedRequest(f"Graph API returned status {e.response.status_code}") from e
        except GraphClientAuthenticationError:
            # Re-raise authentication errors as-is
            raise
        except Exception as e:
            logger.error("Unexpected error fetching messages for user %s: %s", user_id, str(e), exc_info=True)
            raise GraphClientError("An unexpected error occurred during message fetching") from e

    async def fetch_eml_content(self, *, user_id: str, message_id: str) -> bytes:
        """Fetches the raw .eml content of a single email message for a specific user."""
        # Input validation
        if not user_id or not isinstance(user_id, str):
            raise GraphClientError("Invalid user_id provided")
        if not message_id or not isinstance(message_id, str):
            raise GraphClientError("Invalid message_id provided")
            
        url = f"{_GRAPH_BASE_URL}/me/messages/{message_id}/$value"
        logger.info("Fetching EML content for message %s, user %s", message_id, user_id)
        
        try:
            headers = await self._get_auth_headers(user_id)
            response = await self._http_client.get(
                url, 
                headers=headers, 
            )
            response.raise_for_status()
            
            content_size = len(response.content)
            logger.info("Successfully fetched EML content for message %s, user %s (%d bytes)", 
                       message_id, user_id, content_size)
            
            return response.content
            
        except httpx.TimeoutException as e:
            logger.error("Timeout fetching EML content for message %s, user %s: %s", 
                        message_id, user_id, str(e))
            raise GraphClientError(f"Request timeout for message {message_id}") from e
        except httpx.HTTPStatusError as e:
            logger.error("HTTP error fetching EML content for message %s, user %s: %s - %s", 
                        message_id, user_id, e.response.status_code, e.response.text)
            raise GraphAPIFailedRequest(f"Graph API returned status {e.response.status_code}") from e
        except GraphClientAuthenticationError:
            # Re-raise authentication errors as-is
            raise
        except Exception as e:
            logger.error("Unexpected error fetching EML content for message %s, user %s: %s", 
                        message_id, user_id, str(e), exc_info=True)
            raise GraphClientError("An unexpected error occurred during EML content fetching") from e