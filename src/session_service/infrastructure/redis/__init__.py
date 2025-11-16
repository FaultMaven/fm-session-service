"""Redis infrastructure module."""

from session_service.infrastructure.redis.client import (
    get_redis_client,
    close_redis_client,
)

__all__ = ["get_redis_client", "close_redis_client"]
