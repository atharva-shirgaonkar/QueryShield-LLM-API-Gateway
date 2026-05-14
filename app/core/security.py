"""
Authentication helpers for password hashing and JWT access tokens.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings


ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
API_KEY_PREFIX = "qs_"
API_KEY_RANDOM_BYTES = 32

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True when a plaintext password matches a stored bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(
    subject: str | int,
    expires_delta: timedelta | None = None,
    claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT access token for a user subject."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
    }
    if claims:
        payload.update(claims)
        payload["sub"] = str(subject)
        payload["exp"] = expire

    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token, including signature and expiry."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise JWTError("Could not validate access token") from exc

    if not payload.get("sub"):
        raise JWTError("Access token is missing a subject")

    return payload


def generate_api_key() -> str:
    """Generate a secure raw API key to show once to the user."""
    return f"{API_KEY_PREFIX}{secrets.token_hex(API_KEY_RANDOM_BYTES)}"


def hash_api_key(api_key: str) -> str:
    """Return the SHA256 hash stored for API key lookup."""
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()
