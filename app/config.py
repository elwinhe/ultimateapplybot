"""
app/config.py

Centralized configuration for the application.
Loads settings from a .env file using Pydantic.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Centralized configuration for the application.
    Loads settings from a .env file.
    """
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    # Redis/Celery
    REDIS_URL: str

    # Microsoft Graph API
    CLIENT_ID: str
    CLIENT_SECRET: str
    REDIRECT_URI: str # Required for the OAuth flow

    # AWS S3
    S3_BUCKET_NAME: str
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str
    S3_ENDPOINT_URL: str | None = None

    # PostgreSQL
    DATABASE_URL: str

    # Email processing settings
    REDIS_LAST_SEEN_EXPIRY: int = 604800  # 7 days in seconds

    # JWT Authentication
    JWT_SECRET_KEY: str

    # Celery Configuration
    CELERY_SECRET_KEY: str | None = None

# Create a single, importable instance for the rest of the application to use.
settings = Settings()