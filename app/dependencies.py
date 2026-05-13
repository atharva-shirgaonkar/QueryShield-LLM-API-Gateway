"""Shared FastAPI dependencies."""

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import User


def _authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Return the authenticated user from a Bearer access token."""
    if authorization is None:
        raise _authentication_error()

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _authentication_error()

    try:
        payload = decode_access_token(token.strip())
        user_id = int(payload["sub"])
    except (JWTError, KeyError, TypeError, ValueError):
        raise _authentication_error() from None

    user = await db.get(User, user_id)
    if user is None:
        raise _authentication_error()

    return user
