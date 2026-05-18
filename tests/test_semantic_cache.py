from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
import pytest_asyncio

from app.api.routes import query as query_routes
from app.core.embeddings import get_embedding
from app.core.redis_client import get_redis
from app.core.semantic_cache import (
    cosine_similarity,
    find_semantic_match,
    store_semantic_cache,
)
from app.main import app


SEMANTIC_RESPONSE = {
    "response": "Machine learning lets systems learn patterns from data.",
    "model": query_routes.OPENAI_MODEL,
    "prompt_tokens": 5,
    "completion_tokens": 8,
    "total_tokens": 13,
}


@pytest_asyncio.fixture
async def fake_redis():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await redis.flushall()
    yield redis
    await redis.flushall()
    await redis.aclose()


@pytest.fixture
def mock_openai_client(monkeypatch):
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=SEMANTIC_RESPONSE["response"]))],
        model=query_routes.OPENAI_MODEL,
        usage=SimpleNamespace(
            prompt_tokens=SEMANTIC_RESPONSE["prompt_tokens"],
            completion_tokens=SEMANTIC_RESPONSE["completion_tokens"],
            total_tokens=SEMANTIC_RESPONSE["total_tokens"],
        ),
    )
    create = AsyncMock(return_value=completion)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(query_routes, "client", client)
    return create


@pytest.fixture
def semantic_cache_dependencies(fake_redis):
    async def override_get_redis():
        yield fake_redis

    app.dependency_overrides[get_redis] = override_get_redis
    yield
    app.dependency_overrides.pop(get_redis, None)


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_cosine_similarity_returns_one_for_identical_vectors():
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_similarity_returns_zero_for_orthogonal_vectors():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_returns_value_between_zero_and_one_for_similar_vectors():
    similarity = cosine_similarity([1.0, 1.0], [1.0, 0.5])

    assert 0.0 < similarity < 1.0


def test_get_embedding_returns_list_of_floats():
    embedding = get_embedding("What is machine learning?")

    assert len(embedding) > 0
    assert isinstance(embedding, list)
    assert all(isinstance(value, float) for value in embedding)


def test_get_embedding_returns_same_embedding_for_same_text():
    first_embedding = get_embedding("What is machine learning?")
    second_embedding = get_embedding("What is machine learning?")

    assert first_embedding == second_embedding


@pytest.mark.asyncio
async def test_find_semantic_match_returns_none_when_redis_is_empty(fake_redis):
    match = await find_semantic_match("What is machine learning?", fake_redis)

    assert match is None


@pytest.mark.asyncio
async def test_find_semantic_match_returns_cached_response_above_threshold(fake_redis):
    await store_semantic_cache(
        "What is machine learning?",
        SEMANTIC_RESPONSE,
        fake_redis,
    )

    match = await find_semantic_match("Can you explain machine learning?", fake_redis)

    assert match == SEMANTIC_RESPONSE


@pytest.mark.asyncio
async def test_find_semantic_match_returns_none_below_threshold(fake_redis):
    await store_semantic_cache(
        "What is machine learning?",
        SEMANTIC_RESPONSE,
        fake_redis,
    )

    match = await find_semantic_match("How do I bake sourdough bread?", fake_redis)

    assert match is None


@pytest.mark.asyncio
async def test_query_first_call_returns_semantic_cached_false(
    test_client,
    auth_token,
    semantic_cache_dependencies,
    mock_openai_client,
):
    response = await test_client.post(
        "/query",
        json={"prompt": "What is machine learning?"},
        headers=auth_headers(auth_token),
    )

    assert response.status_code == 200
    assert response.json()["cached"] is False
    assert response.json()["semantic_cached"] is False
    mock_openai_client.assert_awaited_once()


@pytest.mark.asyncio
async def test_query_similar_prompt_returns_semantic_cached_true(
    test_client,
    auth_token,
    semantic_cache_dependencies,
    mock_openai_client,
):
    first_response = await test_client.post(
        "/query",
        json={"prompt": "What is machine learning?"},
        headers=auth_headers(auth_token),
    )
    second_response = await test_client.post(
        "/query",
        json={"prompt": "Can you explain machine learning?"},
        headers=auth_headers(auth_token),
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert second_response.json()["cached"] is False
    assert second_response.json()["semantic_cached"] is True
    mock_openai_client.assert_awaited_once()
