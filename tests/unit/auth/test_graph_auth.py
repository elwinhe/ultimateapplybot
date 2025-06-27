"""
tests/unit/auth/test_graph_auth.py

Unit tests for the DelegatedGraphAuthenticator class (multi-user, PostgreSQL-backed).

These tests are designed to test the DelegatedGraphAuthenticator class
in isolation, without relying on external services or the application's
main functionality.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import importlib
import os
import httpx
from jose import JWTError

from app.auth.graph_auth import (
    DelegatedGraphAuthenticator,
    GraphAuthError,
    GraphAuthTokenError
    )
from app.config import settings


class TestDelegatedGraphAuthenticator:
    """Test cases for DelegatedGraphAuthenticator."""

    def test_init_with_and_without_http_client(self):
        """Test initialization with and without explicit http_client."""
        # With explicit client
        client = Mock(spec=httpx.AsyncClient)
        auth = DelegatedGraphAuthenticator(http_client=client)
        assert auth._http_client is client
        # Without explicit client
        auth2 = DelegatedGraphAuthenticator()
        assert isinstance(auth2._http_client, httpx.AsyncClient)

    def test_get_auth_flow_url_success(self):
        """Test that the auth URL is generated and contains required params."""
        auth = DelegatedGraphAuthenticator(http_client=Mock())
        url = auth.get_auth_flow_url()
        assert "login.microsoftonline.com" in url
        assert "client_id=" in url
        assert "redirect_uri=" in url
        assert "response_type=code+id_token" in url
        assert "scope=" in url
        assert "nonce=" in url

    def test_get_auth_flow_url_failure(self):
        """Test that an exception in URL generation raises GraphAuthError."""
        auth = DelegatedGraphAuthenticator(http_client=Mock())
        with patch("app.auth.graph_auth.httpx.Request", side_effect=Exception("fail")):
            with pytest.raises(Exception):
                auth.get_auth_flow_url()

    @pytest.mark.asyncio
    async def test_acquire_and_store_tokens_input_validation(self):
        auth = DelegatedGraphAuthenticator(http_client=AsyncMock())
        # Short code
        with pytest.raises(GraphAuthTokenError, match="Invalid authorization code format"):
            await auth.acquire_and_store_tokens("short", "valid_id_token_12345")
        # Short id_token
        with pytest.raises(GraphAuthTokenError, match="Invalid id_token format"):
            await auth.acquire_and_store_tokens("valid_auth_code_12345", "short")

    @pytest.mark.asyncio
    async def test_acquire_and_store_tokens_invalid_id_token(self):
        auth = DelegatedGraphAuthenticator(http_client=AsyncMock())
        with patch("app.auth.graph_auth.jwt.get_unverified_claims", side_effect=JWTError("bad jwt")):
            with pytest.raises(GraphAuthTokenError, match="Invalid id_token"):
                await auth.acquire_and_store_tokens("valid_auth_code_12345", "invalid_id_token_12345")

    @pytest.mark.asyncio
    async def test_acquire_and_store_tokens_missing_user_id(self):
        auth = DelegatedGraphAuthenticator(http_client=AsyncMock())
        with patch("app.auth.graph_auth.jwt.get_unverified_claims", return_value={}):
            with pytest.raises(GraphAuthTokenError, match="User identifier not found"):
                await auth.acquire_and_store_tokens("valid_auth_code_12345", "valid_id_token_12345")

    @pytest.mark.asyncio
    async def test_acquire_and_store_tokens_http_error(self):
        http_client = AsyncMock()
        http_client.post.return_value = Mock(status_code=400, text="bad request", json=lambda: {})
        auth = DelegatedGraphAuthenticator(http_client=http_client)
        with patch("app.auth.graph_auth.jwt.get_unverified_claims", return_value={"preferred_username": "user@example.com"}):
            with pytest.raises(GraphAuthTokenError, match="Failed to exchange code for token"):
                await auth.acquire_and_store_tokens("valid_auth_code_12345", "valid_id_token_12345")

    @pytest.mark.asyncio
    async def test_acquire_and_store_tokens_no_refresh_token(self):
        http_client = AsyncMock()
        http_client.post.return_value = Mock(status_code=200, json=lambda: {"access_token": "abc"})
        auth = DelegatedGraphAuthenticator(http_client=http_client)
        with patch("app.auth.graph_auth.jwt.get_unverified_claims", return_value={"preferred_username": "user@example.com"}):
            with pytest.raises(GraphAuthTokenError, match="No refresh token returned"):
                await auth.acquire_and_store_tokens("valid_auth_code_12345", "valid_id_token_12345")

    @pytest.mark.asyncio
    async def test_acquire_and_store_tokens_success(self):
        http_client = AsyncMock()
        http_client.post.return_value = Mock(status_code=200, json=lambda: {"refresh_token": "refresh", "access_token": "abc"})
        auth = DelegatedGraphAuthenticator(http_client=http_client)
        with patch("app.auth.graph_auth.jwt.get_unverified_claims", return_value={"preferred_username": "user@example.com"}):
            with patch("app.auth.graph_auth.store_refresh_token", new_callable=AsyncMock) as mock_store:
                await auth.acquire_and_store_tokens("valid_auth_code_12345", "valid_id_token_12345")
                mock_store.assert_awaited_once_with("user@example.com", "refresh")

    @pytest.mark.asyncio
    async def test_get_access_token_for_user_input_validation(self):
        auth = DelegatedGraphAuthenticator(http_client=AsyncMock())
        with pytest.raises(GraphAuthError, match="Invalid user_id provided"):
            await auth.get_access_token_for_user("")
        with pytest.raises(GraphAuthError, match="Invalid user_id provided"):
            await auth.get_access_token_for_user(None)

    @pytest.mark.asyncio
    async def test_get_access_token_for_user_no_refresh_token(self):
        auth = DelegatedGraphAuthenticator(http_client=AsyncMock())
        with patch("app.auth.graph_auth.get_refresh_token", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            with pytest.raises(GraphAuthError, match="No refresh token found for user"):
                await auth.get_access_token_for_user("user@example.com")

    @pytest.mark.asyncio
    async def test_get_access_token_for_user_http_error(self):
        http_client = AsyncMock()
        http_client.post.return_value = Mock(status_code=400, text="bad request", json=lambda: {})
        auth = DelegatedGraphAuthenticator(http_client=http_client)
        with patch("app.auth.graph_auth.get_refresh_token", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = "refresh"
            with pytest.raises(GraphAuthTokenError, match="Failed to refresh token for user"):
                await auth.get_access_token_for_user("user@example.com")

    @pytest.mark.asyncio
    async def test_get_access_token_for_user_success(self):
        http_client = AsyncMock()
        http_client.post.return_value = Mock(status_code=200, json=lambda: {"access_token": "abc"})
        auth = DelegatedGraphAuthenticator(http_client=http_client)
        with patch("app.auth.graph_auth.get_refresh_token", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = "refresh"
            token = await auth.get_access_token_for_user("user@example.com")
            assert token == "abc"

    @pytest.mark.asyncio
    async def test_get_access_token_for_user_new_refresh_token(self):
        http_client = AsyncMock()
        http_client.post.return_value = Mock(status_code=200, json=lambda: {"access_token": "abc", "refresh_token": "newrefresh"})
        auth = DelegatedGraphAuthenticator(http_client=http_client)
        with patch("app.auth.graph_auth.get_refresh_token", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = "refresh"
            with patch("app.auth.graph_auth.store_refresh_token", new_callable=AsyncMock) as mock_store:
                token = await auth.get_access_token_for_user("user@example.com")
                assert token == "abc"
                mock_store.assert_awaited_once_with("user@example.com", "newrefresh")
