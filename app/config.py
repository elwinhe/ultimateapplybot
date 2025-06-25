# app/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8')

    REDIS_URL: str

    TENANT_ID: str
    CLIENT_ID: str
    CLIENT_SECRET: str

    S3_BUCKET_NAME: str
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str
    AWS_REGION: str

    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "emailreader"
    POSTGRES_USER: str = "emailreader_user"
    POSTGRES_PASSWORD: str = "emailreader_password"

    # Email processing settings
    TARGET_MAILBOX: str = "inbox"

    def get_database_url(self) -> str:
        """Construct the database URL from individual components."""
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

# Create a single, importable instance
settings = Settings()