"""Configuration settings for fm-session-service.

Uses Pydantic Settings for environment variable management.
"""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Service metadata
    service_name: str = "fm-session-service"
    service_version: str = "1.0.0"
    environment: str = "development"

    # Server configuration
    host: str = "0.0.0.0"
    port: int = 8002
    debug: bool = False
    log_level: str = "INFO"

    # Redis configuration
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 1
    redis_password: str | None = None
    redis_ssl: bool = False
    redis_decode_responses: bool = True

    # Redis Sentinel configuration (for HA deployments)
    redis_mode: str = "standalone"  # "standalone" or "sentinel"
    redis_sentinel_hosts: str | None = None  # Comma-separated "host:port,host:port"
    redis_master_set: str = "mymaster"  # Sentinel master set name

    # Session configuration
    session_ttl_days: int = 7
    session_ttl_seconds: int = 604800  # 7 days in seconds
    max_sessions_per_user: int = 50
    default_timeout_minutes: int = 180  # 3 hours
    min_timeout_minutes: int = 60  # 1 hour
    max_timeout_minutes: int = 480  # 8 hours

    # CORS configuration
    cors_origins: List[str] = ["*"]
    cors_allow_credentials: bool = True
    cors_allow_methods: List[str] = ["*"]
    cors_allow_headers: List[str] = ["*"]

    # API configuration
    api_v1_prefix: str = "/api/v1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance.

    Returns:
        Settings: Application settings
    """
    return Settings()
