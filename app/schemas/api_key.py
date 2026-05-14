"""Schemas for API key management."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class APIKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class APIKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key_prefix: str
    name: str
    is_active: bool
    created_at: datetime


class APIKeyCreateResponse(APIKeyResponse):
    key: str
