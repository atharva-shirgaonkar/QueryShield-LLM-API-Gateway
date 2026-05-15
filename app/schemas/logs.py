"""Schemas for structured request log payloads."""

from pydantic import BaseModel


class RequestLog(BaseModel):
    request_id: str
    method: str
    path: str
    status_code: int
    duration_ms: float
    user_id: int | None = None
    cached: bool | None = None
    token_count: int | None = None
