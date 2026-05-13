from fastapi import Depends, FastAPI

from app.api.routes import auth_router, query_router
from app.core.config import settings
from app.dependencies import get_current_user
from app.models import User
from app.schemas.auth import UserResponse

app = FastAPI(
    title="QueryShield",
    description="Smart API gateway with LLM cost control",
    version="0.1.0"
)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(query_router, prefix="/query", tags=["query"])

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": "QueryShield",
        "free_tier_limit": settings.free_tier_daily_tokens,
        "pro_tier_limit": settings.pro_tier_daily_tokens
    }


@app.get("/auth/me", response_model=UserResponse)
async def read_current_user(
    current_user: User = Depends(get_current_user),
) -> User:
    return current_user
