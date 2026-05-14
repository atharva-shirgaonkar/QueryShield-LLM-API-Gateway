from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import query as query_routes
from app.core.circuit_breaker import CircuitBreaker
from app.core.redis_client import get_redis
from app.core.security import create_access_token, get_password_hash
from app.main import app
from app.models import APIKey, User


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.store[key] = value
        return True


@pytest.fixture(autouse=True)
def api_key_test_dependencies(monkeypatch):
    fake_redis = FakeRedis()

    async def override_get_redis():
        yield fake_redis

    app.dependency_overrides[get_redis] = override_get_redis
    monkeypatch.setattr(query_routes.settings, "free_tier_daily_tokens", 1000)
    query_routes.openai_circuit_breaker = CircuitBreaker()

    yield fake_redis

    app.dependency_overrides.pop(get_redis, None)
    query_routes.openai_circuit_breaker = CircuitBreaker()


def mock_openai_client(
    monkeypatch,
    *,
    reply: str = "API key request worked",
    model: str = query_routes.OPENAI_MODEL,
    prompt_tokens: int = 5,
    completion_tokens: int = 7,
    total_tokens: int = 12,
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


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_key(test_client, auth_token: str, name: str = "test key"):
    return await test_client.post(
        "/keys",
        json={"name": name},
        headers=auth_headers(auth_token),
    )


async def create_other_user(db_session) -> User:
    user = User(
        email="other-user@example.com",
        hashed_password=get_password_hash("OtherPassword123"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_create_api_key_with_valid_jwt_returns_raw_key(test_client, auth_token):
    response = await create_key(test_client, auth_token, "production")

    assert response.status_code == 201
    data = response.json()
    assert data["key"].startswith("qs_")
    assert data["key_prefix"] == data["key"][:8]
    assert data["name"] == "production"
    assert data["is_active"] is True
    assert "key_hash" not in data


@pytest.mark.asyncio
async def test_create_api_key_no_token_returns_401(test_client):
    response = await test_client.post("/keys", json={"name": "no token"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


@pytest.mark.asyncio
async def test_list_api_keys_with_valid_jwt_exposes_no_raw_values(
    test_client,
    auth_token,
):
    created = await create_key(test_client, auth_token, "ci key")
    assert created.status_code == 201

    response = await test_client.get("/keys", headers=auth_headers(auth_token))

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "ci key"
    assert "key" not in data[0]
    assert "key_hash" not in data[0]


@pytest.mark.asyncio
async def test_delete_api_key_with_valid_jwt_deactivates_key(
    test_client,
    auth_token,
    db_session,
):
    created = await create_key(test_client, auth_token)
    key_id = created.json()["id"]

    response = await test_client.delete(
        f"/keys/{key_id}",
        headers=auth_headers(auth_token),
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    api_key = await db_session.get(APIKey, key_id)
    assert api_key is not None
    assert api_key.is_active is False


@pytest.mark.asyncio
async def test_delete_api_key_for_different_user_returns_404(
    test_client,
    auth_token,
    db_session,
):
    other_user = await create_other_user(db_session)
    other_token = create_access_token(subject=other_user.id)
    created = await create_key(test_client, other_token, "other user's key")
    key_id = created.json()["id"]

    response = await test_client.delete(
        f"/keys/{key_id}",
        headers=auth_headers(auth_token),
    )

    assert response.status_code in {403, 404}


@pytest.mark.asyncio
async def test_query_with_valid_api_key_returns_200(
    test_client,
    auth_token,
    monkeypatch,
):
    mock_openai_client(monkeypatch, reply="The gateway accepts API keys.")
    created = await create_key(test_client, auth_token)
    raw_key = created.json()["key"]

    response = await test_client.post(
        "/query",
        json={"prompt": "Use the API key."},
        headers=auth_headers(raw_key),
    )

    assert response.status_code == 200
    assert response.json() == {
        "response": "The gateway accepts API keys.",
        "model": query_routes.OPENAI_MODEL,
        "prompt_tokens": 5,
        "completion_tokens": 7,
        "total_tokens": 12,
        "cached": False,
    }


@pytest.mark.asyncio
async def test_query_with_deactivated_api_key_returns_401(
    test_client,
    auth_token,
    monkeypatch,
):
    create = mock_openai_client(monkeypatch)
    created = await create_key(test_client, auth_token)
    data = created.json()
    raw_key = data["key"]

    deleted = await test_client.delete(
        f"/keys/{data['id']}",
        headers=auth_headers(auth_token),
    )
    assert deleted.status_code == 200

    response = await test_client.post(
        "/query",
        json={"prompt": "This should be rejected."},
        headers=auth_headers(raw_key),
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"
    create.assert_not_called()


@pytest.mark.asyncio
async def test_query_with_fake_api_key_returns_401(
    test_client,
    monkeypatch,
):
    create = mock_openai_client(monkeypatch)

    response = await test_client.post(
        "/query",
        json={"prompt": "Fake key should not work."},
        headers=auth_headers("qs_not-a-real-key"),
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"
    create.assert_not_called()
