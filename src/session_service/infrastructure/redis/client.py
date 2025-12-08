"""Redis client for fm-session-service.

Provides async Redis connection management with Sentinel support for HA.
"""

import logging
from typing import Optional

import redis.asyncio as redis
from fm_core_lib.infrastructure import get_redis_client as get_redis_from_factory

from session_service.config import get_settings

logger = logging.getLogger(__name__)

# Global Redis client instance
_redis_client: Optional[redis.Redis] = None


async def get_redis_client() -> redis.Redis:
    """Get or create Redis client with Sentinel support.

    Uses fm-core-lib factory for deployment-neutral Redis configuration:
    - Standalone mode (development, self-hosted)
    - Sentinel mode (enterprise K8s with HA)

    Environment Variables:
        REDIS_MODE: "standalone" (default) or "sentinel"

        For standalone:
            REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD

        For sentinel:
            REDIS_SENTINEL_HOSTS: Comma-separated "host:port,host:port"
            REDIS_MASTER_SET: Master set name (default: "mymaster")
            REDIS_DB, REDIS_PASSWORD

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

    # Create new connection using Sentinel-aware factory
    settings = get_settings()

    try:
        _redis_client = await get_redis_from_factory(
            mode=settings.redis_mode,
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password,
            sentinel_hosts=settings.redis_sentinel_hosts,
            master_set=settings.redis_master_set,
        )

        mode_display = settings.redis_mode.upper()
        if settings.redis_mode == "sentinel":
            logger.info(
                f"Redis connection established (SENTINEL): "
                f"master_set={settings.redis_master_set}, "
                f"sentinels={settings.redis_sentinel_hosts}, "
                f"db={settings.redis_db}"
            )
        else:
            logger.info(
                f"Redis connection established (STANDALONE): "
                f"{settings.redis_host}:{settings.redis_port}/{settings.redis_db}"
            )

        return _redis_client

    except Exception as e:
        logger.error(f"Failed to connect to Redis ({settings.redis_mode} mode): {e}")
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
