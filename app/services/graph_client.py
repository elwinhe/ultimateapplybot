# app/services/graph_client.py
from __future__ import annotations

import logging
from typing import Iterable, List

import httpx

from app.auth.graph_auth import acquire_token  # <-- your MSAL helper
from app.models.email import Email

_LOGGER = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class GraphClient:
    # Thin wrapper around Microsoft Graph for message retrieval.
    def __init__(self, tenant_id: str, client_id: str, client_secret: str) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret

    async def _get_headers(self) -> dict[str, str]:
        token = await acquire_token(
            tenant_id=self._tenant_id,
            client_id=self._client_id,
            client_secret=self._client_secret,
            scope="https://graph.microsoft.com/.default",
        )
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async def fetch_messages(
        self,
        top: int = 10,
        select: Iterable[str] | None = None,
        mailbox: str = "me",
    ) -> List[Email]:
        """
        Fetch the latest *top* messages for the given mailbox
        and map them to the internal ``Email`` model.

        Args:
            top: max number of messages to return.
            select: MS Graph $select projection.
            mailbox: ``"me"`` or ``"users/{user_id}"``.

        Returns:
            List of ``Email`` domain objects.
        """
        params: dict[str, str | int] = {"$top": top, "$orderby": "receivedDateTime DESC"}
        if select:
            params["$select"] = ",".join(select)

        url = f"{_GRAPH_BASE}/{mailbox}/messages"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=await self._get_headers(), params=params)
            resp.raise_for_status()
            data = resp.json().get("value", [])

        emails: List[Email] = []
        for raw in data:
            try:
                emails.append(Email.model_validate(raw))
            except Exception as exc:  # noqa: BLE001
                _LOGGER.warning("Skipping message %s due to validation error: %s", raw.get("id"), exc)

        return emails
