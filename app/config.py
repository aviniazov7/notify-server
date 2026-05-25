from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings. Override via environment variables or .env file."""

    app_name: str = "Notify Server"
    api_prefix: str = "/api/v1"
    session_ttl_seconds: int = 3600  # session lifetime (1 hour)
    heartbeat_seconds: int = 10  # interval for the "still connected" heartbeat push
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
