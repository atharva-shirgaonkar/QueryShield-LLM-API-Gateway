from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import query as query_routes
from app.api.routes import usage as usage_routes
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


@pytest.fixture(autouse=True)
def usage_test_dependencies(monkeypatch):
    fake_redis = FakeRedis()

    async def override_get_redis():
        yield fake_redis

    app.dependency_overrides[get_redis] = override_get_redis
    monkeypatch.setattr(usage_routes.settings, "free_tier_daily_tokens", 1000)
    monkeypatch.setattr(query_routes.settings, "free_tier_daily_tokens", 1000)
    query_routes.openai_circuit_breaker = CircuitBreaker()

    yield fake_redis

    app.dependency_overrides.pop(get_redis, None)
    query_routes.openai_circuit_breaker = CircuitBreaker()


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def mock_openai_client(
    monkeypatch,
    *,
    prompt_tokens: int = 8,
    completion_tokens: int = 12,
    total_tokens: int = 20,
) -> AsyncMock:
    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Usage counted"))],
        model=query_routes.OPENAI_MODEL,
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


async def add_usage(
    db_session,
    user_id: int,
    *,
    prompt: str = "Seeded prompt",
    total_tokens: int = 100,
    cached: bool = False,
) -> Usage:
    usage = Usage(
        user_id=user_id,
        prompt=prompt,
        prompt_tokens=total_tokens // 2,
        completion_tokens=total_tokens - (total_tokens // 2),
        total_tokens=total_tokens,
        model=query_routes.OPENAI_MODEL,
        cached=cached,
    )
    db_session.add(usage)
    await db_session.commit()
    await db_session.refresh(usage)
    return usage


@pytest.mark.asyncio
async def test_usage_me_with_valid_token_returns_summary(
    test_client,
    auth_token,
    test_user,
    db_session,
):
    await add_usage(db_session, test_user.id, total_tokens=125, cached=False)
    await add_usage(db_session, test_user.id, total_tokens=125, cached=True)

    response = await test_client.get("/usage/me", headers=auth_headers(auth_token))

    assert response.status_code == 200
    assert response.json() == {
        "total_tokens_used": 125,
        "remaining_tokens": 875,
        "tier": "free",
        "percentage_used": 12.5,
    }


@pytest.mark.asyncio
async def test_usage_me_no_token_returns_401(test_client):
    response = await test_client.get("/usage/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_usage_history_with_valid_token_returns_items(
    test_client,
    auth_token,
    test_user,
    db_session,
):
    await add_usage(db_session, test_user.id, prompt="First", total_tokens=10)
    await add_usage(db_session, test_user.id, prompt="Second", total_tokens=20)

    response = await test_client.get("/usage/history", headers=auth_headers(auth_token))

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["page"] == 1
    assert data["page_size"] == 10
    assert len(data["items"]) == 2
    assert {
        "prompt",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "model",
        "cached",
        "created_at",
    }.issubset(data["items"][0])


@pytest.mark.asyncio
async def test_usage_history_with_pagination_params_returns_structure(
    test_client,
    auth_token,
    test_user,
    db_session,
):
    for index in range(7):
        await add_usage(
            db_session,
            test_user.id,
            prompt=f"Prompt {index}",
            total_tokens=10 + index,
        )

    response = await test_client.get(
        "/usage/history?page=1&page_size=5",
        headers=auth_headers(auth_token),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 7
    assert data["page"] == 1
    assert data["page_size"] == 5
    assert len(data["items"]) == 5


@pytest.mark.asyncio
async def test_usage_me_after_query_reflects_updated_token_count(
    test_client,
    auth_token,
    monkeypatch,
):
    mock_openai_client(
        monkeypatch,
        prompt_tokens=9,
        completion_tokens=11,
        total_tokens=20,
    )

    query_response = await test_client.post(
        "/query",
        json={"prompt": "Track this request."},
        headers=auth_headers(auth_token),
    )
    usage_response = await test_client.get(
        "/usage/me",
        headers=auth_headers(auth_token),
    )

    assert query_response.status_code == 200
    assert usage_response.status_code == 200
    assert usage_response.json() == {
        "total_tokens_used": 20,
        "remaining_tokens": 980,
        "tier": "free",
        "percentage_used": 2.0,
    }
