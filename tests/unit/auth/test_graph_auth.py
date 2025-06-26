# tests/auth/test_graph_auth.py

import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.auth.graph_auth import DelegatedGraphAuthenticator, GraphAuthError


class TestDelegatedGraphAuthenticator:
    """Test suite for DelegatedGraphAuthenticator class."""

    def test_initialization(self, mocker):
        """Test that the authenticator initializes correctly with settings."""
        with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal:
            with patch('app.auth.graph_auth.redis.Redis') as mock_redis:
                authenticator = DelegatedGraphAuthenticator()
                
                mock_msal.assert_called_once()
                # Check that it was called with the correct arguments
                call_args = mock_msal.call_args
                assert call_args[0][0] == '912704d5-823e-47f8-93e1-f5b013687c2b'  # CLIENT_ID
                assert 'authority' in call_args[1]
                assert call_args[1]['authority'] == 'https://login.microsoftonline.com/common'

    @pytest.mark.asyncio
    async def test_get_access_token_for_user_success(self, mocker):
        """Test successful token acquisition using refresh token."""
        with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
            mock_msal_app = mock_msal_class.return_value
            
            # Mock Redis to return a refresh token
            mock_redis = Mock()
            mock_redis.get.return_value = 'test_refresh_token'
            
            with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                mock_redis_class.from_url.return_value = mock_redis
                
                # Mock successful token acquisition
                mock_msal_app.acquire_token_by_refresh_token.return_value = {
                    'access_token': 'fake-access-token-123',
                    'expires_in': 3600
                }

                authenticator = DelegatedGraphAuthenticator()
                token = await authenticator.get_access_token_for_user()
                
                assert token == 'fake-access-token-123'
                mock_redis.get.assert_called_once()
                mock_msal_app.acquire_token_by_refresh_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_access_token_for_user_no_refresh_token(self, mocker):
        """Test error handling when no refresh token is found."""
        with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
            mock_redis = Mock()
            mock_redis.get.return_value = None  # No refresh token
            
            with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                mock_redis_class.from_url.return_value = mock_redis

                authenticator = DelegatedGraphAuthenticator()
                
                with pytest.raises(GraphAuthError, match="No refresh token found for user"):
                    await authenticator.get_access_token_for_user()

    @pytest.mark.asyncio
    async def test_get_access_token_for_user_refresh_failure(self, mocker):
        """Test error handling for refresh token failure."""
        with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
            mock_msal_app = mock_msal_class.return_value
            
            # Mock Redis to return a refresh token
            mock_redis = Mock()
            mock_redis.get.return_value = 'test_refresh_token'
            
            with patch('app.auth.graph_auth.redis.Redis') as mock_redis_class:
                mock_redis_class.from_url.return_value = mock_redis
                
                # Mock failed token acquisition
                mock_msal_app.acquire_token_by_refresh_token.return_value = {
                    'error': 'invalid_grant',
                    'error_description': 'Refresh token expired'
                }

                authenticator = DelegatedGraphAuthenticator()
                
                with pytest.raises(GraphAuthError, match="Refresh token expired"):
                    await authenticator.get_access_token_for_user()


class TestDelegatedGraphAuthenticatorSingleton:
    """Test suite for the singleton delegated_auth_client instance."""

    def test_singleton_instance_exists(self):
        """Test that the singleton instance is created and accessible."""
        from app.auth.graph_auth import delegated_auth_client
        assert delegated_auth_client is not None
        assert isinstance(delegated_auth_client, DelegatedGraphAuthenticator)

    def test_singleton_instance_is_same_object(self):
        """Test that the singleton instance is always the same object."""
        from app.auth.graph_auth import delegated_auth_client as instance1
        from app.auth.graph_auth import delegated_auth_client as instance2
        
        assert instance1 is instance2


class TestGraphAuthError:
    """Test suite for GraphAuthError exception."""

    def test_graph_auth_error_inheritance(self):
        """Test that GraphAuthError inherits from Exception."""
        error = GraphAuthError("Test error")
        assert isinstance(error, Exception)
        assert str(error) == "Test error"

    def test_graph_auth_error_with_message(self):
        """Test that GraphAuthError can be created with a custom message."""
        message = "Custom authentication error"
        error = GraphAuthError(message)
        assert str(error) == message
