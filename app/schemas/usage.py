"""Schemas for usage and admin reporting."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.user import UserTier


class UsageSummary(BaseModel):
    total_tokens_used: int
    remaining_tokens: int
    tier: UserTier
    percentage_used: float


class UsageHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    prompt: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str
    cached: bool
    created_at: datetime


class UsageHistoryResponse(BaseModel):
    items: list[UsageHistoryItem]
    total: int
    page: int
    page_size: int


class AdminStats(BaseModel):
    total_users: int
    total_tokens: int
    total_queries: int
    cache_hit_rate: float
    circuit_breaker_state: str
