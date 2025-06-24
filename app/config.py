# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # model_config will automatically look for these in a .env file
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    # Redis/Celery
    REDIS_URL: str

    # Microsoft Graph API
    TENANT_ID: str
    CLIENT_ID: str
    CLIENT_SECRET: str

    # AWS S3
    S3_BUCKET_NAME: str
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str

# Create a single, importable instance
settings = Settings()