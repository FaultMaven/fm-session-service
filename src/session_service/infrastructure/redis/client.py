"""Redis client for fm-session-service.

Provides async Redis connection management.
"""

import logging
from typing import Optional

import redis.asyncio as redis

from session_service.config import get_settings

logger = logging.getLogger(__name__)

# Global Redis client instance
_redis_client: Optional[redis.Redis] = None


async def get_redis_client() -> redis.Redis:
    """Get or create Redis client.

    Returns:
        redis.Redis: Async Redis client

    Raises:
        ConnectionError: If Redis connection fails
    """
    global _redis_client

    if _redis_client is not None:
        try:
            # Test connection
            await _redis_client.ping()
            return _redis_client
        except Exception as e:
            logger.warning(f"Existing Redis connection failed: {e}, reconnecting...")
            _redis_client = None

    # Create new connection
    settings = get_settings()

    try:
        _redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password,
            ssl=settings.redis_ssl,
            decode_responses=settings.redis_decode_responses,
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
        )

        # Test connection
        await _redis_client.ping()
        logger.info(
            f"Redis connection established: {settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
        )

        return _redis_client

    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        _redis_client = None
        raise ConnectionError(f"Redis connection failed: {e}")


async def close_redis_client():
    """Close Redis client connection."""
    global _redis_client

    if _redis_client is not None:
        try:
            await _redis_client.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.warning(f"Error closing Redis connection: {e}")
        finally:
            _redis_client = None
