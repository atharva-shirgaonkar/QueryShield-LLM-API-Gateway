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


@pytest.fixture(autouse=True)
def admin_test_dependencies(monkeypatch):
    fake_redis = FakeRedis()

    async def override_get_redis():
        yield fake_redis

    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Mocked"))],
            model=query_routes.OPENAI_MODEL,
            usage=SimpleNamespace(
                prompt_tokens=1,
                completion_tokens=1,
                total_tokens=2,
            ),
        )
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr(query_routes, "client", client)
    app.dependency_overrides[get_redis] = override_get_redis
    query_routes.openai_circuit_breaker = CircuitBreaker()

    yield fake_redis

    app.dependency_overrides.pop(get_redis, None)
    query_routes.openai_circuit_breaker = CircuitBreaker()


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def add_usage(
    db_session,
    user_id: int,
    *,
    total_tokens: int,
    cached: bool,
) -> Usage:
    usage = Usage(
        user_id=user_id,
        prompt="Admin stats prompt",
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
async def test_admin_stats_with_superuser_token_returns_stats(
    test_client,
    superuser_token,
    test_user,
    db_session,
):
    await add_usage(db_session, test_user.id, total_tokens=30, cached=False)
    await add_usage(db_session, test_user.id, total_tokens=30, cached=True)

    response = await test_client.get(
        "/admin/stats",
        headers=auth_headers(superuser_token),
    )

    assert response.status_code == 200
    assert response.json() == {
        "total_users": 2,
        "total_tokens": 30,
        "total_queries": 2,
        "cache_hit_rate": 50.0,
        "circuit_breaker_state": "CLOSED",
    }


@pytest.mark.asyncio
async def test_admin_stats_with_regular_user_token_returns_403(
    test_client,
    auth_token,
):
    response = await test_client.get("/admin/stats", headers=auth_headers(auth_token))

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin access required"


@pytest.mark.asyncio
async def test_admin_stats_no_token_returns_401(test_client):
    response = await test_client.get("/admin/stats")

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_admin_stats_fields_present(test_client, superuser_token):
    response = await test_client.get(
        "/admin/stats",
        headers=auth_headers(superuser_token),
    )

    assert response.status_code == 200
    assert set(response.json()) == {
        "total_users",
        "total_tokens",
        "total_queries",
        "cache_hit_rate",
        "circuit_breaker_state",
    }
