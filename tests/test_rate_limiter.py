import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
import pytest_asyncio

from app.api.routes import query as query_routes
from app.core import rate_limiter
from app.core.redis_client import get_redis
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models import User, UserTier


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def fake_redis():
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await redis.flushall()
    yield redis
    await redis.flushall()
    await redis.aclose()


@pytest.fixture
def rate_limit_dependencies(fake_redis, monkeypatch):
    async def override_get_redis():
        yield fake_redis

    completion = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="Rate limited response"))],
        model=query_routes.OPENAI_MODEL,
        usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5),
    )
    create = AsyncMock(return_value=completion)
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )

    app.dependency_overrides[get_redis] = override_get_redis
    monkeypatch.setattr(query_routes, "client", client)
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
    monkeypatch.setattr(rate_limiter, "RATE_LIMIT_FREE", 3)

    yield create

    app.dependency_overrides.pop(get_redis, None)


async def post_query(test_client, token: str, prompt: str = "Rate limited prompt"):
    return await test_client.post(
        "/query",
        json={"prompt": prompt},
        headers=auth_headers(token),
    )


async def create_user(db_session, email: str, tier: UserTier = UserTier.FREE) -> User:
    user = User(
        email=email,
        hashed_password=get_password_hash("CorrectHorse123"),
        tier=tier,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_free_user_within_limit_returns_200(
    test_client,
    auth_token,
    rate_limit_dependencies,
):
    responses = [await post_query(test_client, auth_token) for _ in range(3)]

    assert [response.status_code for response in responses] == [200, 200, 200]


@pytest.mark.asyncio
async def test_free_user_exceeds_limit_returns_429(
    test_client,
    auth_token,
    rate_limit_dependencies,
):
    for _ in range(3):
        await post_query(test_client, auth_token)

    response = await post_query(test_client, auth_token)

    assert response.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_429_response_includes_detail_and_retry_after(
    test_client,
    auth_token,
    rate_limit_dependencies,
):
    for _ in range(3):
        await post_query(test_client, auth_token)

    response = await post_query(test_client, auth_token)

    assert response.json() == {
        "detail": "Rate limit exceeded. Try again in 60 seconds.",
        "retry_after": 60,
    }
    assert response.headers["Retry-After"] == "60"


@pytest.mark.asyncio
async def test_rate_limit_response_includes_limit_headers(
    test_client,
    auth_token,
    rate_limit_dependencies,
):
    for _ in range(3):
        await post_query(test_client, auth_token)

    response = await post_query(test_client, auth_token)

    assert response.headers["X-RateLimit-Limit"] == "3"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert int(response.headers["X-RateLimit-Reset"]) > 0


@pytest.mark.asyncio
async def test_pro_user_is_not_blocked_at_free_tier_limit(
    test_client,
    db_session,
    rate_limit_dependencies,
):
    pro_user = await create_user(db_session, "pro-rate-limit@example.com", UserTier.PRO)
    pro_token = create_access_token(subject=pro_user.id)

    responses = [await post_query(test_client, pro_token) for _ in range(4)]

    assert [response.status_code for response in responses] == [200, 200, 200, 200]
    assert responses[-1].headers["X-RateLimit-Limit"] == "60"


@pytest.mark.asyncio
async def test_rate_limit_resets_after_window_expires(
    test_client,
    auth_token,
    rate_limit_dependencies,
    monkeypatch,
):
    monkeypatch.setattr(rate_limiter, "RATE_LIMIT_WINDOW", 1)
    monkeypatch.setattr(query_routes, "RATE_LIMIT_WINDOW", 1)

    for _ in range(3):
        await post_query(test_client, auth_token)

    exceeded = await post_query(test_client, auth_token)
    await asyncio.sleep(1.1)
    reset_response = await post_query(test_client, auth_token)

    assert exceeded.status_code == 429
    assert reset_response.status_code == 200
    assert reset_response.json()["rate_limit_remaining"] == 2


@pytest.mark.asyncio
async def test_different_users_have_independent_rate_limit_counters(
    test_client,
    auth_token,
    db_session,
    rate_limit_dependencies,
):
    other_user = await create_user(db_session, "other-rate-limit@example.com")
    other_token = create_access_token(subject=other_user.id)

    for _ in range(3):
        await post_query(test_client, auth_token)

    first_user_exceeded = await post_query(test_client, auth_token)
    other_user_response = await post_query(test_client, other_token)

    assert first_user_exceeded.status_code == 429
    assert other_user_response.status_code == 200
    assert other_user_response.json()["rate_limit_remaining"] == 2
