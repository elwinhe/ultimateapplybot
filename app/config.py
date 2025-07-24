"""
app/config.py

Centralized configuration for the application.
Loads settings from a .env file using Pydantic.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    """
    Centralized configuration for the application.
    Loads settings from a .env file.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra='ignore'
    )

    # Redis/Celery
    REDIS_URL: str

    # Microsoft Graph API
    CLIENT_ID: str
    CLIENT_SECRET: str
    REDIRECT_URI: str # Required for the OAuth flow

    # AWS SQS settings
    SQS_QUEUE_URL: Optional[str] = None

    # PostgreSQL
    DATABASE_URL: str

    # Email processing settings
    REDIS_LAST_SEEN_EXPIRY: int = 604800  # 7 days in seconds

    # JWT Authentication
    JWT_SECRET_KEY: str

    # Celery Configuration
    CELERY_SECURITY_KEY: str | None = None

    SKIP_S3: bool = True

# Create a single, importable instance for the rest of the application to use.
settings = Settings()