"""
tests/conftest.py

Shared test fixtures and configuration for the EmailReader test suite.
"""
import pytest
import redis
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.config import settings
from app.auth.graph_auth import DelegatedGraphAuthenticator
from app.services.graph_client import GraphClient
from app.services.postgres_client import postgres_client
from app.services.s3_client import s3_client

# Redis key for storing refresh tokens
REFRESH_TOKEN_KEY = f"user_refresh_token:{settings.TARGET_EXTERNAL_USER}"

@pytest.fixture(scope="session")
def test_redis_client():
    """Provides a Redis client for testing."""
    try:
        client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        client.ping()
        return client
    except Exception:
        # Return None if Redis is not available (e.g., running tests from host)
        return None

@pytest.fixture(autouse=True)
def setup_test_authentication(test_redis_client):
    """
    Automatically sets up test authentication for all tests.
    This ensures tests have a valid refresh token available.
    """
    if test_redis_client is not None:
        # Store a test refresh token in Redis
        test_refresh_token = "test_refresh_token_for_testing"
        test_redis_client.set(REFRESH_TOKEN_KEY, test_refresh_token)
        
        yield
        
        # Clean up after test
        test_redis_client.delete(REFRESH_TOKEN_KEY)
    else:
        # Skip Redis setup if not available
        yield

@pytest.fixture
def mock_delegated_auth():
    """
    Mocks the delegated auth client to return a valid access token.
    """
    mock_auth = MagicMock(spec=DelegatedGraphAuthenticator)
    mock_auth.get_access_token_for_user = AsyncMock(return_value="test_access_token")
    yield mock_auth

@pytest.fixture
def mock_email_tasks_dependencies():
    """
    Provides mocked dependencies for email task tests.
    """
    mock_auth = MagicMock(spec=DelegatedGraphAuthenticator)
    mock_auth.get_access_token_for_user = AsyncMock(return_value="test_access_token")
    
    with patch('app.tasks.email_tasks._get_auth_client', return_value=mock_auth):
        with patch('app.tasks.email_tasks.postgres_client') as mock_postgres:
            with patch('app.tasks.email_tasks.s3_client') as mock_s3:
                with patch('app.tasks.email_tasks.redis.Redis') as mock_redis_class:
                    mock_redis = MagicMock()
                    mock_redis_class.from_url.return_value = mock_redis
                    mock_redis.get.return_value = datetime.now(timezone.utc).isoformat()
                    
                    # Create a mock HTTP client
                    mock_http_client = AsyncMock()
                    
                    yield {
                        'auth': mock_auth,
                        'postgres': mock_postgres,
                        's3': mock_s3,
                        'redis': mock_redis,
                        'http_client': mock_http_client
                    }

@pytest.fixture
def mock_http_client():
    """
    Provides a mocked HTTP client for testing.
    """
    return AsyncMock()

@pytest.fixture
def mock_email_with_invoice():
    """
    Provides a test email that matches filtering criteria (contains "invoice").
    """
    from app.models.email import Email, EmailAddress, Body
    
    return Email(
        id="invoice_email_123",
        subject="Your Monthly Invoice",
        received_date_time=datetime(2025, 6, 25, 12, 0, tzinfo=timezone.utc),
        body=Body(contentType="html", content="<p>Invoice content</p>"),
        from_address=EmailAddress(name="Billing", address="billing@example.com"),
        to_addresses=[EmailAddress(name="User", address="user@example.com")],
        cc_addresses=[],
        bcc_addresses=[],
        has_attachments=False,
        attachments=None
    )

@pytest.fixture
def mock_email_no_match():
    """
    Provides a test email that doesn't match filtering criteria.
    """
    from app.models.email import Email, EmailAddress, Body
    
    return Email(
        id="no_match_email_789",
        subject="Hello World",
        received_date_time=datetime(2025, 6, 25, 10, 0, tzinfo=timezone.utc),
        body=Body(contentType="text", content="Just saying hello"),
        from_address=EmailAddress(name="Friend", address="friend@example.com"),
        to_addresses=[EmailAddress(name="User", address="user@example.com")],
        cc_addresses=[],
        bcc_addresses=[],
        has_attachments=False,
        attachments=None
    )