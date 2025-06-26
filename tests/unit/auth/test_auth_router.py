"""
tests/unit/auth/test_auth_router.py

Unit tests for the OAuth2 authentication router endpoints.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v1.auth_router import login, auth_callback, get_auth_client, process_auth_code
from app.auth.graph_auth import GraphAuthError, DelegatedGraphAuthenticator
from app.main import app

class TestAuthRouter:
    """Test cases for the authentication router endpoints."""

    @pytest.mark.asyncio
    async def test_login_success(self):
        """Test successful login redirect."""
        # Mock the auth client dependency
        mock_auth_client = MagicMock(spec=DelegatedGraphAuthenticator)
        mock_auth_client.get_auth_flow_url.return_value = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=test&response_type=code&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fapi%2Fv1%2Fauth%2Fcallback&scope=Mail.Read+offline_access+openid+profile"
        
        with patch('app.api.v1.auth_router.get_auth_client', return_value=mock_auth_client):
            # Call the login endpoint
            response = await login(auth_client=mock_auth_client)
            
            # Verify the response is a redirect
            assert response.status_code == 307
            assert "login.microsoftonline.com" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_login_error(self):
        """Test login when auth client fails."""
        # Mock the auth client to raise an error
        mock_auth_client = MagicMock(spec=DelegatedGraphAuthenticator)
        mock_auth_client.get_auth_flow_url.side_effect = Exception("Auth URL generation failed")
        
        with pytest.raises(HTTPException) as exc_info:
            await login(auth_client=mock_auth_client)
        
        assert exc_info.value.status_code == 500
        assert "Failed to initiate authentication" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_auth_callback_success(self):
        """Test successful authentication callback."""
        # Mock the auth client
        mock_auth_client = MagicMock(spec=DelegatedGraphAuthenticator)
        mock_auth_client.acquire_token_by_auth_code = AsyncMock()
        
        # Call the auth callback endpoint
        response = await auth_callback(code="valid_auth_code", auth_client=mock_auth_client)
        
        # Verify the response
        assert response.status == "success"
        assert "Authentication successful" in response.message

    @pytest.mark.asyncio
    async def test_auth_callback_error(self):
        """Test authentication callback with error."""
        # Mock the auth client to raise an error
        mock_auth_client = MagicMock(spec=DelegatedGraphAuthenticator)
        mock_auth_client.acquire_token_by_auth_code = AsyncMock(side_effect=GraphAuthError("Invalid authorization code"))
        
        # Call the auth callback endpoint
        with pytest.raises(HTTPException) as exc_info:
            await auth_callback(code="invalid_code", auth_client=mock_auth_client)
        
        # Verify the response
        assert exc_info.value.status_code == 400
        assert "Invalid authorization code" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_auth_callback_missing_code(self):
        """Test authentication callback with missing code."""
        # Mock the auth client
        mock_auth_client = MagicMock(spec=DelegatedGraphAuthenticator)
        mock_auth_client.acquire_token_by_auth_code = AsyncMock()
        
        # Test with empty code
        with pytest.raises(HTTPException) as exc_info:
            await auth_callback(code="", auth_client=mock_auth_client)
        
        # Should fail validation
        assert exc_info.value.status_code == 400
        assert "Invalid authorization code format" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_process_auth_code_success(self):
        """Test successful auth code processing."""
        # Mock the auth client
        mock_auth_client = MagicMock(spec=DelegatedGraphAuthenticator)
        mock_auth_client.acquire_token_by_auth_code = AsyncMock()
        
        # Call the process function
        response = await process_auth_code("valid_code", mock_auth_client)
        
        # Verify the response
        assert response.status == "success"
        assert "Authentication successful" in response.message
        mock_auth_client.acquire_token_by_auth_code.assert_awaited_once_with("valid_code")

    @pytest.mark.asyncio
    async def test_process_auth_code_failure(self):
        """Test auth code processing failure."""
        # Mock the auth client to raise an error
        mock_auth_client = MagicMock(spec=DelegatedGraphAuthenticator)
        mock_auth_client.acquire_token_by_auth_code = AsyncMock(side_effect=GraphAuthError("Token acquisition failed"))
        
        # Call the process function
        with pytest.raises(HTTPException) as exc_info:
            await process_auth_code("invalid_code", mock_auth_client)
        
        # Verify the error
        assert exc_info.value.status_code == 400
        assert "Token acquisition failed" in str(exc_info.value.detail) 