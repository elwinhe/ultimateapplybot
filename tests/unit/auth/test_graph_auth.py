# tests/auth/test_graph_auth.py

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone
import importlib
import os

from app.auth.graph_auth import (
    DelegatedGraphAuthenticator, 
    GraphAuthError, 
    GraphAuthValidationError, 
    GraphAuthTokenError
)
from app.config import settings


class TestDelegatedGraphAuthenticator:
    """Test cases for DelegatedGraphAuthenticator."""

    def test_init_success(self):
        """Test successful initialization with valid settings."""
        with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
            with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                mock_redis_class.from_url.return_value = Mock()
                
                authenticator = DelegatedGraphAuthenticator()
                
                assert authenticator is not None
                mock_msal_class.assert_called_once()
                mock_redis_class.from_url.assert_called_once()

    def test_init_missing_client_id(self):
        """Test initialization fails when CLIENT_ID is missing."""
        with patch.dict(os.environ, {"CLIENT_ID": ""}):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            with pytest.raises(graph_auth_module.GraphAuthValidationError, match="CLIENT_ID is required"):
                graph_auth_module.DelegatedGraphAuthenticator()

    def test_init_missing_client_secret(self):
        """Test initialization fails when CLIENT_SECRET is missing."""
        with patch.dict(os.environ, {"CLIENT_SECRET": ""}):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            with pytest.raises(graph_auth_module.GraphAuthValidationError, match="CLIENT_SECRET is required"):
                graph_auth_module.DelegatedGraphAuthenticator()

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
            "TARGET_EXTERNAL_USER": "dummy@example.com"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
                mock_app = mock_msal_class.return_value
                mock_app.get_authorization_request_url.return_value = "https://login.microsoftonline.com/..."
                
                with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                    mock_redis_class.from_url.return_value = Mock()
                    
                    authenticator = graph_auth_module.DelegatedGraphAuthenticator()
                    url = authenticator.get_auth_flow_url()
                    
                    assert url == "https://login.microsoftonline.com/..."
                    mock_app.get_authorization_request_url.assert_called_once()

    def test_get_auth_flow_url_failure(self):
        """Test auth flow URL generation failure."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "dummy-client-secret",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
                mock_app = mock_msal_class.return_value
                mock_app.get_authorization_request_url.side_effect = Exception("MSAL error")
                
                with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                    mock_redis_class.from_url.return_value = Mock()
                    
                    authenticator = graph_auth_module.DelegatedGraphAuthenticator()
                    
                    with pytest.raises(graph_auth_module.GraphAuthError, match="Failed to generate authentication URL"):
                        authenticator.get_auth_flow_url()

    def test_acquire_token_by_auth_code_success(self):
        """Test successful token acquisition with auth code."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "dummy-client-secret",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
                mock_app = mock_msal_class.return_value
                mock_app.acquire_token_by_authorization_code.return_value = {
                    'access_token': 'fake-access-token',
                    'refresh_token': 'fake-refresh-token',
                    'expires_in': 3600
                }
                
                with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                    mock_redis = Mock()
                    mock_redis_class.from_url.return_value = mock_redis
                    
                    authenticator = graph_auth_module.DelegatedGraphAuthenticator()
                    authenticator.acquire_token_by_auth_code("valid_auth_code_123")
                    
                    mock_app.acquire_token_by_authorization_code.assert_called_once()
                    mock_redis.set.assert_called_once()

    def test_acquire_token_by_auth_code_invalid_code(self):
        """Test token acquisition with invalid auth code."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "dummy-client-secret",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
                with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                    mock_redis_class.from_url.return_value = Mock()
                    
                    authenticator = graph_auth_module.DelegatedGraphAuthenticator()
                    
                    with pytest.raises(graph_auth_module.GraphAuthValidationError, match="Invalid authorization code format"):
                        authenticator.acquire_token_by_auth_code("short")

    def test_acquire_token_by_auth_code_no_refresh_token(self):
        """Test token acquisition when no refresh token is returned."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "dummy-client-secret",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
                mock_app = mock_msal_class.return_value
                mock_app.acquire_token_by_authorization_code.return_value = {
                    'access_token': 'fake-access-token',
                    'expires_in': 3600
                    # No refresh_token
                }
                
                with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                    mock_redis_class.from_url.return_value = Mock()
                    
                    authenticator = graph_auth_module.DelegatedGraphAuthenticator()
                    
                    with pytest.raises(graph_auth_module.GraphAuthTokenError, match="No refresh token returned"):
                        authenticator.acquire_token_by_auth_code("valid_auth_code_123")

    def test_acquire_token_by_auth_code_msal_error(self):
        """Test token acquisition when MSAL returns an error."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "dummy-client-secret",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
                mock_app = mock_msal_class.return_value
                mock_app.acquire_token_by_authorization_code.return_value = {
                    'error': 'invalid_grant',
                    'error_description': 'Authorization code expired'
                }
                
                with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                    mock_redis_class.from_url.return_value = Mock()
                    
                    authenticator = graph_auth_module.DelegatedGraphAuthenticator()
                    
                    with pytest.raises(graph_auth_module.GraphAuthTokenError, match="Authorization code expired"):
                        authenticator.acquire_token_by_auth_code("valid_auth_code_123")

    @pytest.mark.asyncio
    async def test_get_access_token_for_user_success(self):
        """Test successful token acquisition using refresh token."""
        with patch.dict(os.environ, {
            "CLIENT_ID": "dummy-client-id",
            "CLIENT_SECRET": "dummy-client-secret",
            "REDIRECT_URI": "http://localhost/callback",
            "TARGET_EXTERNAL_USER": "dummy@example.com"
        }):
            importlib.reload(importlib.import_module('app.config'))
            graph_auth_module = importlib.reload(importlib.import_module('app.auth.graph_auth'))
            with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
                mock_app = mock_msal_class.return_value

                # Mock Redis to return a refresh token
                mock_redis = Mock()
                mock_redis.get.return_value = 'test_refresh_token'

                with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                    mock_redis_class.from_url.return_value = mock_redis

                    # Mock successful token acquisition
                    mock_app.acquire_token_by_refresh_token.return_value = {
                        'access_token': 'fake-access-token-123',
                        'expires_in': 3600
                    }

                    authenticator = graph_auth_module.DelegatedGraphAuthenticator()
                    token = await authenticator.get_access_token_for_user()

                    assert token == 'fake-access-token-123'

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
            with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
                mock_redis = Mock()
                mock_redis.get.return_value = None  # No refresh token

                with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                    mock_redis_class.from_url.return_value = mock_redis

                    authenticator = graph_auth_module.DelegatedGraphAuthenticator()

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
            with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
                mock_app = mock_msal_class.return_value

                # Mock Redis to return a refresh token
                mock_redis = Mock()
                mock_redis.get.return_value = 'test_refresh_token'

                with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                    mock_redis_class.from_url.return_value = mock_redis

                    # Mock failed token acquisition
                    mock_app.acquire_token_by_refresh_token.return_value = {
                        'error': 'invalid_grant',
                        'error_description': 'Refresh token expired'
                    }

                    authenticator = graph_auth_module.DelegatedGraphAuthenticator()

                    with pytest.raises(graph_auth_module.GraphAuthTokenError, match="Refresh token expired"):
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
            with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
                mock_app = mock_msal_class.return_value

                # Mock Redis to return a refresh token
                mock_redis = Mock()
                mock_redis.get.return_value = 'old_refresh_token'

                with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                    mock_redis_class.from_url.return_value = mock_redis

                    # Mock successful token acquisition with new refresh token
                    mock_app.acquire_token_by_refresh_token.return_value = {
                        'access_token': 'new-access-token',
                        'refresh_token': 'new_refresh_token',
                        'expires_in': 3600
                    }

                    authenticator = graph_auth_module.DelegatedGraphAuthenticator()
                    token = await authenticator.get_access_token_for_user()

                    assert token == 'new-access-token'
                    # Verify the new refresh token was stored
                    mock_redis.set.assert_called_once()
