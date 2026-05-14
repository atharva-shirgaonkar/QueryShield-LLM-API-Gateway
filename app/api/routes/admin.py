"""Admin-only system reporting routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.routes.query as query_routes
from app.core.database import get_db
from app.dependencies import get_current_user
from app.models import Usage, User
from app.schemas.usage import AdminStats


router = APIRouter()


@router.get("/stats", response_model=AdminStats)
async def read_admin_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AdminStats:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    total_users = await db.scalar(select(func.count()).select_from(User))
    total_tokens = await db.scalar(
        select(func.coalesce(func.sum(Usage.total_tokens), 0)).where(
            Usage.cached.is_(False)
        )
    )
    total_queries = await db.scalar(select(func.count()).select_from(Usage))
    cache_hits = await db.scalar(
        select(func.count()).select_from(Usage).where(Usage.cached.is_(True))
    )

    total_queries = int(total_queries or 0)
    cache_hits = int(cache_hits or 0)
    cache_hit_rate = (
        round((cache_hits / total_queries) * 100, 2) if total_queries > 0 else 0.0
    )

    return AdminStats(
        total_users=int(total_users or 0),
        total_tokens=int(total_tokens or 0),
        total_queries=total_queries,
        cache_hit_rate=cache_hit_rate,
        circuit_breaker_state=query_routes.openai_circuit_breaker.state.value,
    )
