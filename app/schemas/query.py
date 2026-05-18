"""Schemas for OpenAI proxy requests and responses."""

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    prompt: str = Field(min_length=1)


class QueryResponse(BaseModel):
    response: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached: bool
    semantic_cached: bool
    rate_limit_remaining: int
