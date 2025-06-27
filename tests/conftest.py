"""
tests/conftest.py

Shared test fixtures and configuration for the EmailReader test suite.
Updated for multi-user architecture.
"""
import pytest
import redis
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from app.config import settings
from app.services.graph_client import GraphClient
from app.services.postgres_client import postgres_client
from app.services.s3_client import s3_client

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
def setup_test_database():
    """
    Automatically sets up test database state for all tests.
    This ensures tests have clean, predictable data.
    """
    # This fixture can be used to set up test users in PostgreSQL
    # For now, it's a placeholder that can be extended as needed
    yield

@pytest.fixture
def mock_graph_client():
    """
    Provides a mocked GraphClient for testing.
    """
    mock_client = AsyncMock(spec=GraphClient)
    mock_client.fetch_messages = AsyncMock(return_value=[])
    mock_client.fetch_eml_content = AsyncMock(return_value=b"test email content")
    return mock_client

@pytest.fixture
def mock_postgres_client():
    """
    Provides a mocked PostgreSQL client for testing.
    """
    mock_client = AsyncMock()
    mock_client.execute = AsyncMock()
    mock_client.fetch_all = AsyncMock(return_value=[])
    mock_client.fetch_one = AsyncMock(return_value=None)
    return mock_client

@pytest.fixture
def mock_s3_client():
    """
    Provides a mocked S3 client for testing.
    """
    mock_client = AsyncMock()
    mock_client.upload_eml_file = AsyncMock(return_value="test/s3/key.eml")
    return mock_client

@pytest.fixture
def mock_redis_client():
    """
    Provides a mocked Redis client for testing.
    """
    mock_client = MagicMock()
    mock_client.get = MagicMock(return_value=None)
    mock_client.setex = MagicMock()
    mock_client.delete = MagicMock()
    return mock_client

@pytest.fixture
def sample_users():
    """
    Provides a list of sample user IDs for multi-user testing.
    """
    return [
        "user1@example.com",
        "user2@example.com", 
        "user3@example.com"
    ]

@pytest.fixture
def sample_auth_tokens(sample_users):
    """
    Provides sample auth token records for multi-user testing.
    """
    return [
        {"user_id": user_id, "encrypted_refresh_token": f"token_for_{user_id}"}
        for user_id in sample_users
    ]

@pytest.fixture
def mock_email_tasks_dependencies():
    """
    Provides mocked dependencies for email task tests in multi-user architecture.
    """
    with patch('app.tasks.email_tasks.postgres_client') as mock_postgres:
        with patch('app.tasks.email_tasks.s3_client') as mock_s3:
            with patch('app.tasks.email_tasks.redis_client') as mock_redis:
                with patch('app.tasks.email_tasks.GraphClient') as mock_graph_class:
                    mock_graph = AsyncMock()
                    mock_graph_class.return_value = mock_graph
                    
                    yield {
                        'postgres': mock_postgres,
                        's3': mock_s3,
                        'redis': mock_redis,
                        'graph': mock_graph
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

@pytest.fixture(autouse=True)
def mock_postgres_in_decorator():
    """
    Auto-used fixture that mocks the postgres_client specifically where it's
    imported by the decorator module. This prevents the decorator from
    running real database logic during both unit and E2E tests, allowing
    test-specific fixtures to manage the database lifecycle instead.
    """
    with patch("app.tasks.decorators.postgres_client", new_callable=AsyncMock) as mock_pg:
        yield mock_pg