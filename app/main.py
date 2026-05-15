from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import admin_router, auth_router, keys_router, query_router, usage_router
from app.core.config import settings
from app.core.logger import get_logger
from app.core.middleware import RequestLoggingMiddleware


logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("QueryShield started successfully")
    yield
    logger.info("QueryShield shutting down")


app = FastAPI(
    title="QueryShield",
    description="Smart API gateway with LLM cost control",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(RequestLoggingMiddleware)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(keys_router, prefix="/keys", tags=["keys"])
app.include_router(query_router, prefix="/query", tags=["query"])
app.include_router(usage_router, prefix="/usage", tags=["usage"])
app.include_router(admin_router, prefix="/admin", tags=["admin"])

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": "QueryShield",
        "free_tier_limit": settings.free_tier_daily_tokens,
        "pro_tier_limit": settings.pro_tier_daily_tokens
    }
