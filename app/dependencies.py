"""Shared FastAPI dependencies."""

from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token, hash_api_key
from app.models import APIKey, User


def _authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _get_bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise _authentication_error()

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _authentication_error()

    return token.strip()


async def _get_user_from_jwt_token(token: str, db: AsyncSession) -> User | None:
    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (JWTError, KeyError, TypeError, ValueError):
        return None

    return await db.get(User, user_id)


async def _get_user_from_api_key_token(token: str, db: AsyncSession) -> User | None:
    api_key = await db.scalar(
        select(APIKey).where(
            APIKey.key_hash == hash_api_key(token),
            APIKey.is_active.is_(True),
        )
    )
    if api_key is None:
        return None

    user = await db.get(User, api_key.user_id)
    if user is None:
        return None

    api_key.last_used_at = datetime.now(timezone.utc)
    await db.commit()
    return user


async def get_current_user_from_api_key(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Return the authenticated user from a Bearer API key."""
    token = _get_bearer_token(authorization)
    user = await _get_user_from_api_key_token(token, db)
    if user is None:
        raise _authentication_error()

    return user


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Return the authenticated user from a JWT or API key bearer token."""
    token = _get_bearer_token(authorization)

    user = await _get_user_from_jwt_token(token, db)
    if user is not None:
        return user

    user = await _get_user_from_api_key_token(token, db)
    if user is not None:
        return user

    raise _authentication_error()
