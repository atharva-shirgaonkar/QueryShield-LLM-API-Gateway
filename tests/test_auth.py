import pytest

from tests.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD


@pytest.mark.asyncio
async def test_register_success(test_client):
    response = await test_client.post(
        "/auth/register",
        json={"email": "new-user@example.com", "password": "NewPassword123"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "new-user@example.com"
    assert data["tier"] == "free"
    assert isinstance(data["id"], int)
    assert "created_at" in data
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_400(test_client, test_user):
    response = await test_client.post(
        "/auth/register",
        json={"email": test_user.email, "password": "AnotherPassword123"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Email is already registered"


@pytest.mark.asyncio
async def test_login_valid_credentials_returns_jwt(test_client, test_user):
    response = await test_client.post(
        "/auth/login",
        json={"email": TEST_USER_EMAIL, "password": TEST_USER_PASSWORD},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str)
    assert data["access_token"]


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(test_client, test_user):
    response = await test_client.post(
        "/auth/login",
        json={"email": TEST_USER_EMAIL, "password": "WrongPassword123"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password"


@pytest.mark.asyncio
async def test_auth_me_valid_token_returns_user_info(test_client, test_user, auth_token):
    response = await test_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {auth_token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_user.id
    assert data["email"] == test_user.email
    assert data["tier"] == "free"
    assert "created_at" in data


@pytest.mark.asyncio
async def test_auth_me_no_token_returns_401(test_client):
    response = await test_client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"
