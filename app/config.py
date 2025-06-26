"""
app/config.py

Centralized configuration for the application.
Loads settings from a .env file using Pydantic.
"""
from __future__ import annotations

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Defines all application settings, loading them from environment variables
    or a .env file. Pydantic provides type validation on startup.
    """
    # model_config will automatically look for these in a .env file
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    # Redis/Celery
    REDIS_URL: str

    # Microsoft Graph API - Delegated Auth Flow
    # For delegated auth with PublicClientApplication, only CLIENT_ID is required.
    # CLIENT_SECRET is not needed for public client flows.
    TENANT_ID: str  # Still needed for authority URL construction
    CLIENT_ID: str
    CLIENT_SECRET: Optional[str] = None  # Not needed for delegated auth
    
    # Delegated Auth Specific
    # These must be set to enable the delegated auth flow for external users.
    REDIRECT_URI: Optional[str] = None
    TARGET_EXTERNAL_USER: Optional[str] = None

    S3_BUCKET_NAME: str
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str
    S3_ENDPOINT_URL: Optional[str] = None  # For testing with moto mock service

    DATABASE_URL: str

    # --- Email Processing ---
    # A default value is appropriate here as it's not a secret.
    REDIS_LAST_SEEN_EXPIRY: int = 604800  # 7 days in seconds

# Create a single, importable instance for the rest of the application to use.
settings = Settings()