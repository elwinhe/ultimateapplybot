"""
tests/unit/auth/test_graph_auth.py

Unit tests for the DelegatedGraphAuthenticator class.

These tests are designed to test the DelegatedGraphAuthenticator class
in isolation, without relying on external services or the application's
main functionality.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import importlib
import os
import httpx

from app.auth.graph_auth import (
    DelegatedGraphAuthenticator
    )
from app.config import settings


class TestDelegatedGraphAuthenticator:
    """Test cases for DelegatedGraphAuthenticator."""

    def test_init_success(self):
        """Test successful initialization with all required environment variables."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "dummy-client-secret",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com",
            "REDIS_URL": "redis://localhost:6379"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            
            with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                mock_redis_class.from_url.return_value = Mock()
                authenticator = graph_auth_module.DelegatedGraphAuthenticator()
                assert authenticator is not None

    def test_init_missing_client_id(self):
        """Test initialization fails when CLIENT_ID is missing."""
        with patch.dict(os.environ, {"CLIENT_ID": ""}):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            with pytest.raises(graph_auth_module.GraphAuthValidationError, match="CLIENT_ID is required"):
                graph_auth_module.DelegatedGraphAuthenticator()

    def test_init_missing_client_secret(self):
        """Test initialization succeeds when CLIENT_SECRET is missing (public client)."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com",
            "REDIS_URL": "redis://localhost:6379"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            
            with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                mock_redis_class.from_url.return_value = Mock()
                # Should not raise an error - public clients don't need client secret
                authenticator = graph_auth_module.DelegatedGraphAuthenticator()
                assert authenticator is not None

    def test_init_missing_redirect_uri(self):
        """Test initialization fails when REDIRECT_URI is missing."""
        with patch.dict(os.environ, {"REDIRECT_URI": ""}):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            with pytest.raises(graph_auth_module.GraphAuthValidationError, match="REDIRECT_URI is required"):
                graph_auth_module.DelegatedGraphAuthenticator()

    def test_init_missing_target_user(self):
        """Test initialization fails when TARGET_EXTERNAL_USER is missing."""
        with patch.dict(os.environ, {"TARGET_EXTERNAL_USER": ""}):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            with pytest.raises(graph_auth_module.GraphAuthValidationError, match="TARGET_EXTERNAL_USER is required"):
                graph_auth_module.DelegatedGraphAuthenticator()

    def test_get_auth_flow_url_success(self):
        """Test successful generation of auth flow URL."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "dummy-client-secret",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com",
            "REDIS_URL": "redis://localhost:6379"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            
            with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                mock_redis_class.from_url.return_value = Mock()
                authenticator = graph_auth_module.DelegatedGraphAuthenticator()
                auth_url = authenticator.get_auth_flow_url()
                
                assert "login.microsoftonline.com" in auth_url
                assert "client_id=dummy-client-id" in auth_url
                assert "redirect_uri=http%3A%2F%2Flocalhost%2Fcallback" in auth_url

    def test_get_auth_flow_url_failure(self):
        """Test auth flow URL generation failure."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "dummy-client-secret",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com",
            "REDIS_URL": "redis://localhost:6379"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            
            with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                mock_redis_class.from_url.return_value = Mock()
                authenticator = graph_auth_module.DelegatedGraphAuthenticator()
                
                # Mock httpx.Request to raise an exception
                with patch('app.auth.graph_auth.httpx.Request', side_effect=Exception("URL generation failed")):
                    with pytest.raises(graph_auth_module.GraphAuthError, match="Failed to generate authentication URL"):
                        authenticator.get_auth_flow_url()

    @pytest.mark.asyncio
    async def test_acquire_token_by_auth_code_success(self):
        """Test successful token acquisition with auth code."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "dummy-client-secret",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            
            mock_http_client = AsyncMock()
            mock_response = Mock()  # Use regular Mock for response
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {
                'access_token': 'fake-access-token',
                'refresh_token': 'fake-refresh-token',
                'expires_in': 3600
            }
            mock_http_client.post.return_value = mock_response
            
            with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                mock_redis = Mock()
                mock_redis_class.from_url.return_value = mock_redis
                # Patch store_refresh_token to avoid real DB call
                with patch('app.auth.graph_auth.store_refresh_token', new_callable=AsyncMock) as mock_store_token:
                    authenticator = graph_auth_module.DelegatedGraphAuthenticator(http_client=mock_http_client)
                    await authenticator.acquire_token_by_auth_code("valid_auth_code_123")
                    mock_http_client.post.assert_called_once()
                    mock_store_token.assert_awaited_once_with(
                        "dummy@example.com", 'fake-refresh-token'
                    )

    @pytest.mark.asyncio
    async def test_acquire_token_by_auth_code_invalid_code(self):
        """Test token acquisition with invalid auth code."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "dummy-client-secret",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            
            with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                mock_redis_class.from_url.return_value = Mock()
                
                authenticator = graph_auth_module.DelegatedGraphAuthenticator()
                
                with pytest.raises(graph_auth_module.GraphAuthValidationError, match="Invalid authorization code format"):
                    await authenticator.acquire_token_by_auth_code("short")

    @pytest.mark.asyncio
    async def test_acquire_token_by_auth_code_no_refresh_token(self):
        """Test token acquisition when no refresh token is returned."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "dummy-client-secret",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            
            mock_http_client = AsyncMock()
            mock_response = Mock()  # Use regular Mock for response
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {
                'access_token': 'fake-access-token',
                'expires_in': 3600
                # No refresh_token
            }
            mock_http_client.post.return_value = mock_response
            
            with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                mock_redis_class.from_url.return_value = Mock()
                
                authenticator = graph_auth_module.DelegatedGraphAuthenticator(http_client=mock_http_client)
                
                with pytest.raises(graph_auth_module.GraphAuthTokenError, match="No refresh token returned"):
                    await authenticator.acquire_token_by_auth_code("valid_auth_code_123")

    @pytest.mark.asyncio
    async def test_acquire_token_by_auth_code_http_error(self):
        """Test token acquisition when HTTP request fails."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "dummy-client-secret",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            
            mock_http_client = AsyncMock()
            mock_response = Mock()  # Use regular Mock for response
            mock_response.text = "invalid_grant"
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "400 Bad Request", request=Mock(), response=mock_response
            )
            mock_response.json.side_effect = Exception("Should not be called")
            mock_http_client.post.return_value = mock_response
            
            with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                mock_redis_class.from_url.return_value = Mock()
                
                authenticator = graph_auth_module.DelegatedGraphAuthenticator(http_client=mock_http_client)
                
                with pytest.raises(graph_auth_module.GraphAuthTokenError, match="Failed to exchange authorization code for token"):
                    await authenticator.acquire_token_by_auth_code("valid_auth_code_123")

    @pytest.mark.asyncio
    async def test_get_access_token_for_user_success(self):
        """Test successful token acquisition using stored refresh token."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "dummy-client-secret",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            
            mock_http_client = AsyncMock()
            mock_response = Mock()  # Use regular Mock for response
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {
                'access_token': 'new-access-token',
                'expires_in': 3600
            }
            mock_http_client.post.return_value = mock_response
            
            # Mock Redis to return a refresh token
            mock_redis = Mock()
            mock_redis.get.return_value = 'test_refresh_token'
            
            with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                mock_redis_class.from_url.return_value = mock_redis
                
                # Mock PostgreSQL client
                with patch('app.auth.graph_auth.get_refresh_token') as mock_get_token:
                    mock_get_token.return_value = 'test_refresh_token'
                    
                    authenticator = graph_auth_module.DelegatedGraphAuthenticator(http_client=mock_http_client)
                    token = await authenticator.get_access_token_for_user()
                    
                    assert token == 'new-access-token'
                    mock_http_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_access_token_for_user_no_refresh_token(self):
        """Test error handling when no refresh token is found."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "dummy-client-secret",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            
            mock_http_client = AsyncMock()
            
            # Mock PostgreSQL client to return no refresh token
            with patch('app.auth.graph_auth.get_refresh_token') as mock_get_token:
                mock_get_token.return_value = None
                
                authenticator = graph_auth_module.DelegatedGraphAuthenticator(http_client=mock_http_client)
                
                with pytest.raises(graph_auth_module.GraphAuthTokenError, match="No refresh token found for user"):
                    await authenticator.get_access_token_for_user()

    @pytest.mark.asyncio
    async def test_get_access_token_for_user_refresh_failure(self):
        """Test error handling for refresh token failure."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "dummy-client-secret",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            
            mock_http_client = AsyncMock()
            mock_response = Mock()  # Use regular Mock for response
            mock_response.text = "invalid_grant"
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "400 Bad Request", request=Mock(), response=mock_response
            )
            mock_response.json.side_effect = Exception("Should not be called")
            mock_http_client.post.return_value = mock_response
            
            # Mock PostgreSQL client to return a refresh token
            with patch('app.auth.graph_auth.get_refresh_token') as mock_get_token:
                mock_get_token.return_value = 'test_refresh_token'
                
                authenticator = graph_auth_module.DelegatedGraphAuthenticator(http_client=mock_http_client)
                
                with pytest.raises(graph_auth_module.GraphAuthTokenError, match="Failed to acquire token via refresh token"):
                    await authenticator.get_access_token_for_user()

    @pytest.mark.asyncio
    async def test_get_access_token_for_user_with_new_refresh_token(self):
        """Test token refresh when a new refresh token is issued."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "dummy-client-secret",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            
            mock_http_client = AsyncMock()
            mock_response = Mock()  # Use regular Mock for response
            mock_response.raise_for_status.return_value = None
            mock_response.json.return_value = {
                'access_token': 'new-access-token',
                'refresh_token': 'new_refresh_token',
                'expires_in': 3600
            }
            mock_http_client.post.return_value = mock_response
            
            # Mock PostgreSQL client to return a refresh token
            with patch('app.auth.graph_auth.get_refresh_token', new_callable=AsyncMock) as mock_get_token:
                mock_get_token.return_value = 'old_refresh_token'
                # Mock the store_refresh_token function
                with patch('app.auth.graph_auth.store_refresh_token', new_callable=AsyncMock) as mock_store_token:
                    authenticator = graph_auth_module.DelegatedGraphAuthenticator(http_client=mock_http_client)
                    token = await authenticator.get_access_token_for_user()
                    assert token == 'new-access-token'
                    mock_http_client.post.assert_called_once()
                    # Verify that the new refresh token was stored
                    mock_store_token.assert_awaited_once_with(
                        "dummy@example.com", 'new_refresh_token'
                    )

    @pytest.mark.asyncio
    async def test_get_access_token_for_user_no_http_client(self):
        """Test error handling when no HTTP client is provided."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "dummy-client-secret",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            
            with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                mock_redis_class.from_url.return_value = Mock()
                
                authenticator = graph_auth_module.DelegatedGraphAuthenticator(http_client=None)

                with pytest.raises(graph_auth_module.GraphAuthError, match="HTTP client not available for async token acquisition"):
                    await authenticator.get_access_token_for_user()
