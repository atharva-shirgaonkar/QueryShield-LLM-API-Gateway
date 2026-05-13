"""Async Redis client setup."""

from collections.abc import AsyncGenerator

from redis.asyncio import Redis

from app.core.config import settings


redis_client = Redis.from_url(settings.redis_url, decode_responses=True)


async def get_redis() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency that provides the shared Redis client."""
    yield redis_client
