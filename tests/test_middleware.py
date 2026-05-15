from uuid import UUID

import pytest


REQUEST_ID_HEADER = "X-Request-ID"


def parse_request_id(value: str) -> UUID:
    return UUID(value)


@pytest.mark.asyncio
async def test_every_response_has_request_id_header(test_client):
    response = await test_client.get("/health")

    assert REQUEST_ID_HEADER in response.headers
    assert response.headers[REQUEST_ID_HEADER]


@pytest.mark.asyncio
async def test_request_id_header_is_valid_uuid(test_client):
    response = await test_client.get("/health")

    request_id = parse_request_id(response.headers[REQUEST_ID_HEADER])

    assert str(request_id) == response.headers[REQUEST_ID_HEADER]


@pytest.mark.asyncio
async def test_different_requests_get_different_request_ids(test_client):
    first_response = await test_client.get("/health")
    second_response = await test_client.get("/health")

    assert first_response.headers[REQUEST_ID_HEADER] != second_response.headers[
        REQUEST_ID_HEADER
    ]


@pytest.mark.asyncio
async def test_health_returns_request_id_header(test_client):
    response = await test_client.get("/health")

    assert response.status_code == 200
    assert REQUEST_ID_HEADER in response.headers


@pytest.mark.asyncio
async def test_register_returns_request_id_header(test_client):
    response = await test_client.post(
        "/auth/register",
        json={
            "email": "new-user@example.com",
            "password": "CorrectHorse123",
        },
    )

    assert response.status_code == 201
    assert REQUEST_ID_HEADER in response.headers
