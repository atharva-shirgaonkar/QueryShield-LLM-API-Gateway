"""Semantic Redis cache helpers for similar prompts."""

import json
from typing import Any
from uuid import uuid4

import numpy as np

from app.core.embeddings import get_embedding


SIMILARITY_THRESHOLD = 0.92
SEMANTIC_CACHE_TTL = 3600
SEMANTIC_CACHE_PREFIX = "semantic:"


def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Return cosine similarity between two vectors as a 0..1 float."""
    array1 = np.asarray(vec1, dtype=float)
    array2 = np.asarray(vec2, dtype=float)

    denominator = np.linalg.norm(array1) * np.linalg.norm(array2)
    if denominator == 0:
        return 0.0

    similarity = float(np.dot(array1, array2) / denominator)
    return max(0.0, min(1.0, similarity))


async def store_semantic_cache(prompt: str, response_data: dict[str, Any], redis) -> None:
    """Store a prompt embedding and response payload in Redis."""
    cache_data = {
        "prompt": prompt,
        "embedding": get_embedding(prompt),
        "response": response_data,
    }
    key = f"{SEMANTIC_CACHE_PREFIX}{uuid4()}"
    await redis.set(key, json.dumps(cache_data), ex=SEMANTIC_CACHE_TTL)


async def find_semantic_match(prompt: str, redis) -> dict[str, Any] | None:
    """Return a cached response for a semantically similar prompt, if present."""
    incoming_embedding = get_embedding(prompt)
    pattern = f"{SEMANTIC_CACHE_PREFIX}*"

    async for key in redis.scan_iter(match=pattern):
        cached = await redis.get(key)
        if cached is None:
            continue

        if isinstance(cached, bytes):
            cached = cached.decode("utf-8")

        try:
            cache_data = json.loads(cached)
        except json.JSONDecodeError:
            continue

        cached_embedding = cache_data.get("embedding")
        cached_response = cache_data.get("response")
        if cached_embedding is None or cached_response is None:
            continue

        similarity = cosine_similarity(incoming_embedding, cached_embedding)
        if similarity >= SIMILARITY_THRESHOLD:
            return cached_response

    return None
