"""Redis cache helpers for OpenAI responses."""

import hashlib
import json
from typing import Any


def get_cache_key(prompt: str) -> str:
    """Return a stable cache key for a normalized prompt."""
    normalized_prompt = prompt.strip().lower()
    prompt_hash = hashlib.sha256(normalized_prompt.encode("utf-8")).hexdigest()
    return f"cache:{prompt_hash}"


async def get_cached_response(key: str, redis) -> dict[str, Any] | None:
    """Fetch and decode a cached JSON response."""
    cached = await redis.get(key)
    if cached is None:
        return None

    if isinstance(cached, bytes):
        cached = cached.decode("utf-8")

    try:
        return json.loads(cached)
    except json.JSONDecodeError:
        return None


async def set_cached_response(
    key: str,
    data: dict[str, Any],
    redis,
    ttl: int = 3600,
) -> None:
    """Store a JSON response in Redis with an expiry."""
    await redis.set(key, json.dumps(data), ex=ttl)
