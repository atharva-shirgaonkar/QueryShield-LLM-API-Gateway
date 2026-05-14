"""Usage reporting routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.usage_service import get_total_tokens_used
from app.dependencies import get_current_user
from app.models import Usage, User, UserTier
from app.schemas.usage import UsageHistoryResponse, UsageSummary


router = APIRouter()


def _token_limit_for_user(user: User) -> int:
    return (
        settings.pro_tier_daily_tokens
        if user.tier == UserTier.PRO
        else settings.free_tier_daily_tokens
    )


@router.get("/me", response_model=UsageSummary)
async def read_my_usage(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UsageSummary:
    total_tokens_used = await get_total_tokens_used(current_user.id, db)
    token_limit = _token_limit_for_user(current_user)
    remaining_tokens = max(token_limit - total_tokens_used, 0)
    percentage_used = (
        round((total_tokens_used / token_limit) * 100, 2) if token_limit > 0 else 0.0
    )

    return UsageSummary(
        total_tokens_used=total_tokens_used,
        remaining_tokens=remaining_tokens,
        tier=current_user.tier,
        percentage_used=percentage_used,
    )


@router.get("/history", response_model=UsageHistoryResponse)
async def read_usage_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UsageHistoryResponse:
    total = await db.scalar(
        select(func.count()).select_from(Usage).where(Usage.user_id == current_user.id)
    )
    result = await db.scalars(
        select(Usage)
        .where(Usage.user_id == current_user.id)
        .order_by(Usage.created_at.desc(), Usage.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    return UsageHistoryResponse(
        items=list(result),
        total=int(total or 0),
        page=page,
        page_size=page_size,
    )
