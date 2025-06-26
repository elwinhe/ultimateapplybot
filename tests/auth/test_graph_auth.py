# tests/auth/test_graph_auth.py

import pytest
from unittest.mock import Mock, patch
from app.auth.graph_auth import GraphAuthenticator, GraphAuthError


class TestGraphAuthenticator:
    """Test suite for GraphAuthenticator class."""

    def test_initialization(self, mocker):
        """Test that the authenticator initializes correctly with settings."""
        with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal:
            authenticator = GraphAuthenticator()
            
            mock_msal.assert_called_once()
            # Check that it was called with the correct arguments
            call_args = mock_msal.call_args
            assert call_args[0][0] == '912704d5-823e-47f8-93e1-f5b013687c2b'  # CLIENT_ID
            assert 'authority' in call_args[1]
            assert 'client_credential' in call_args[1]

    def test_get_access_token_success_new_token(self, mocker):
        """Test successful token acquisition when no cached token exists."""
        with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
            mock_msal_app = mock_msal_class.return_value
            
            # Simulate no cached token
            mock_msal_app.acquire_token_silent.return_value = None
            mock_msal_app.acquire_token_for_client.return_value = {
                'access_token': 'fake-access-token-123',
                'expires_in': 3600
            }

            authenticator = GraphAuthenticator()
            token = authenticator.get_access_token()
            
            assert token == 'fake-access-token-123'
            mock_msal_app.acquire_token_silent.assert_called_once()
            mock_msal_app.acquire_token_for_client.assert_called_once()

    def test_get_access_token_success_cached_token(self, mocker):
        """Test successful token acquisition using cached token."""
        with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
            mock_msal_app = mock_msal_class.return_value
            
            # Simulate cached token exists
            mock_msal_app.acquire_token_silent.return_value = {
                'access_token': 'cached-token-456',
                'expires_in': 1800
            }

            authenticator = GraphAuthenticator()
            token = authenticator.get_access_token()
            
            assert token == 'cached-token-456'
            mock_msal_app.acquire_token_silent.assert_called_once()
            mock_msal_app.acquire_token_for_client.assert_not_called()

    def test_get_access_token_failure_invalid_client(self, mocker):
        """Test error handling for invalid client credentials."""
        with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
            mock_msal_app = mock_msal_class.return_value
            mock_msal_app.acquire_token_silent.return_value = None
            mock_msal_app.acquire_token_for_client.return_value = {
                'error': 'invalid_client',
                'error_description': 'Invalid client secret provided.'
            }

            authenticator = GraphAuthenticator()
            
            with pytest.raises(GraphAuthError, match="Could not acquire token: invalid_client"):
                authenticator.get_access_token()

    def test_get_access_token_failure_unauthorized_client(self, mocker):
        """Test error handling for unauthorized client."""
        with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
            mock_msal_app = mock_msal_class.return_value
            mock_msal_app.acquire_token_silent.return_value = None
            mock_msal_app.acquire_token_for_client.return_value = {
                'error': 'unauthorized_client',
                'error_description': 'The client is not authorized to request an access token.'
            }

            authenticator = GraphAuthenticator()
            
            with pytest.raises(GraphAuthError, match="Could not acquire token: unauthorized_client"):
                authenticator.get_access_token()

    def test_get_access_token_failure_no_error_description(self, mocker):
        """Test error handling when no error description is provided."""
        with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
            mock_msal_app = mock_msal_class.return_value
            mock_msal_app.acquire_token_silent.return_value = None
            mock_msal_app.acquire_token_for_client.return_value = {
                'error': 'unknown_error'
            }

            authenticator = GraphAuthenticator()
            
            with pytest.raises(GraphAuthError, match="Could not acquire token: unknown_error"):
                authenticator.get_access_token()

    def test_get_access_token_failure_empty_response(self, mocker):
        """Test error handling for empty response."""
        with patch('app.auth.graph_auth.ConfidentialClientApplication') as mock_msal_class:
            mock_msal_app = mock_msal_class.return_value
            mock_msal_app.acquire_token_silent.return_value = None
            mock_msal_app.acquire_token_for_client.return_value = {}

            authenticator = GraphAuthenticator()
            
            with pytest.raises(GraphAuthError, match="Could not acquire token: None"):
                authenticator.get_access_token()


class TestGraphAuthenticatorSingleton:
    """Test suite for the singleton graph_authenticator instance."""

    def test_singleton_instance_exists(self):
        """Test that the singleton instance is created and accessible."""
        from app.auth.graph_auth import graph_authenticator
        assert graph_authenticator is not None
        assert isinstance(graph_authenticator, GraphAuthenticator)

    def test_singleton_instance_is_same_object(self):
        """Test that the singleton instance is always the same object."""
        from app.auth.graph_auth import graph_authenticator as instance1
        from app.auth.graph_auth import graph_authenticator as instance2
        
        assert instance1 is instance2

    def test_singleton_get_access_token(self, mocker):
        """Test that the singleton instance can acquire tokens."""
        # Mock the singleton's _app attribute directly
        from app.auth.graph_auth import graph_authenticator
        
        mock_app = mocker.Mock()
        mock_app.acquire_token_silent.return_value = None
        mock_app.acquire_token_for_client.return_value = {
            'access_token': 'singleton-token-789',
            'expires_in': 3600
        }
        
        # Replace the singleton's _app with our mock
        graph_authenticator._app = mock_app
        
        token = graph_authenticator.get_access_token()
        assert token == 'singleton-token-789'


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
