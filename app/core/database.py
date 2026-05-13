"""
Async SQLAlchemy setup for QueryShield.

The engine is the application-wide connection pool. Sessions are short-lived
objects created from that pool for each request, background task, or script.
"""

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that gives one database session to a request.

    The `async with` block closes the session when the request finishes, even if
    the route raises an error.
    """
    async with AsyncSessionLocal() as session:
        yield session


async def check_database_connection() -> None:
    """
    Run a tiny query so startup scripts/tests can prove PostgreSQL is reachable.
    """
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def close_database_connections() -> None:
    """Dispose the async engine's connection pool during application shutdown."""
    await engine.dispose()
