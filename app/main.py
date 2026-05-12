from fastapi import FastAPI
from app.core.config import settings

app = FastAPI(
    title="QueryShield",
    description="Smart API gateway with LLM cost control",
    version="0.1.0"
)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "app": "QueryShield",
        "free_tier_limit": settings.free_tier_daily_tokens,
        "pro_tier_limit": settings.pro_tier_daily_tokens
    }