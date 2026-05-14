"""
User model for authentication, tiering, and cost controls.

Each SQLAlchemy model is a Python class that maps to one database table.
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, String, false, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Enum as SQLEnum

from app.core.database import Base


class UserTier(str, Enum):
    """Allowed subscription tiers for a QueryShield user."""

    FREE = "free"
    PRO = "pro"


class User(Base):
    """Application user stored in the `users` table."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )
    tier: Mapped[UserTier] = mapped_column(
        SQLEnum(
            UserTier,
            name="user_tier",
            values_callable=lambda enum_class: [tier.value for tier in enum_class],
        ),
        default=UserTier.FREE,
        server_default=UserTier.FREE.value,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, email={self.email!r}, tier={self.tier.value!r})"
