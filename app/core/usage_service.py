"""Usage accounting helpers."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models import Usage, User, UserTier


async def get_total_tokens_used(user_id: int, db: AsyncSession) -> int:
    """Return all tokens spent by a user across recorded requests."""
    total_tokens = await db.scalar(
        select(func.coalesce(func.sum(Usage.total_tokens), 0)).where(
            Usage.user_id == user_id
        )
    )
    return int(total_tokens or 0)


def has_exceeded_limit(user: User, total_used: int, settings: Settings) -> bool:
    """Return True when the user's total token usage has reached their tier limit."""
    limit = (
        settings.pro_tier_daily_tokens
        if user.tier == UserTier.PRO
        else settings.free_tier_daily_tokens
    )
    return total_used >= limit
