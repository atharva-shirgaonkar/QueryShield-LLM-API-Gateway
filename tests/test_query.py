from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import query as query_routes
from app.core.circuit_breaker import CircuitBreaker
from app.core.redis_client import get_redis
from app.main import app
from app.models import Usage


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        return True

    async def incr(self, key: str) -> int:
        self.store[key] = int(self.store.get(key, 0)) + 1
        return int(self.store[key])

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    async def ttl(self, key: str) -> int:
        return 60


@pytest.fixture(autouse=True)
def query_test_dependencies(monkeypatch):
    fake_redis = FakeRedis()

    async def override_get_redis():
        yield fake_redis

    app.dependency_overrides[get_redis] = override_get_redis
    monkeypatch.setattr(query_routes.settings, "free_tier_daily_tokens", 1000)
    monkeypatch.setattr(
        query_routes,
        "find_semantic_match",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        query_routes,
        "store_semantic_cache",
        AsyncMock(return_value=None),
    )
    query_routes.openai_circuit_breaker = CircuitBreaker()

    yield fake_redis

    app.dependency_overrides.pop(get_redis, None)
    query_routes.openai_circuit_breaker = CircuitBreaker()


def mock_openai_client(
    monkeypatch,
    *,
    reply: str = "Mocked OpenAI response",
    model: str = query_routes.OPENAI_MODEL,
    prompt_tokens: int = 4,
    completion_tokens: int = 6,
    total_tokens: int = 10,
) -> AsyncMock:
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=reply))],
        model=model,
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        ),
    )
    create = AsyncMock(return_value=completion)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(query_routes, "client", client)
    return create


async def post_query(test_client, prompt: str, token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    return await test_client.post("/query", json={"prompt": prompt}, headers=headers)


@pytest.mark.asyncio
async def test_query_no_token_returns_401(test_client):
    response = await post_query(test_client, "Hello")

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_query_empty_prompt_returns_422(test_client, auth_token):
    response = await post_query(test_client, "", auth_token)

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_valid_token_mocked_openai_returns_200(
    test_client,
    auth_token,
    monkeypatch,
):
    create = mock_openai_client(
        monkeypatch,
        reply="Here is the answer.",
        prompt_tokens=7,
        completion_tokens=5,
        total_tokens=12,
    )

    response = await post_query(test_client, "Explain caching.", auth_token)

    assert response.status_code == 200
    assert response.json() == {
        "response": "Here is the answer.",
        "model": query_routes.OPENAI_MODEL,
        "prompt_tokens": 7,
        "completion_tokens": 5,
        "total_tokens": 12,
        "cached": False,
        "semantic_cached": False,
        "rate_limit_remaining": 9,
    }
    create.assert_awaited_once_with(
        model=query_routes.OPENAI_MODEL,
        messages=[{"role": "user", "content": "Explain caching."}],
    )


@pytest.mark.asyncio
async def test_query_same_prompt_twice_returns_cached_second_time(
    test_client,
    auth_token,
    monkeypatch,
):
    create = mock_openai_client(
        monkeypatch,
        reply="Cached answer.",
        prompt_tokens=3,
        completion_tokens=4,
        total_tokens=7,
    )

    first_response = await post_query(test_client, "Repeatable prompt", auth_token)
    second_response = await post_query(test_client, "Repeatable prompt", auth_token)

    assert first_response.status_code == 200
    assert first_response.json()["cached"] is False
    assert second_response.status_code == 200
    assert second_response.json() == {
        "response": "Cached answer.",
        "model": query_routes.OPENAI_MODEL,
        "prompt_tokens": 3,
        "completion_tokens": 4,
        "total_tokens": 7,
        "cached": True,
        "semantic_cached": False,
        "rate_limit_remaining": 8,
    }
    create.assert_awaited_once()


@pytest.mark.asyncio
async def test_query_user_exceeded_token_limit_returns_429(
    test_client,
    auth_token,
    test_user,
    db_session,
    monkeypatch,
):
    create = mock_openai_client(monkeypatch)
    db_session.add(
        Usage(
            user_id=test_user.id,
            prompt="Already spent",
            prompt_tokens=query_routes.settings.free_tier_daily_tokens,
            completion_tokens=0,
            total_tokens=query_routes.settings.free_tier_daily_tokens,
            model=query_routes.OPENAI_MODEL,
        )
    )
    await db_session.commit()

    response = await post_query(test_client, "This should hit the limit.", auth_token)

    assert response.status_code == 429
    assert (
        response.json()["detail"]
        == "Token limit reached for your tier. Please upgrade to pro."
    )
    create.assert_not_called()


@pytest.mark.asyncio
async def test_query_circuit_breaker_open_returns_503(
    test_client,
    auth_token,
    monkeypatch,
):
    mock_openai_client(monkeypatch)
    query_routes.openai_circuit_breaker._open()

    response = await post_query(test_client, "Will the circuit allow this?", auth_token)

    assert response.status_code == 503
    assert (
        response.json()["detail"]
        == "Service temporarily unavailable. Please try again shortly."
    )
