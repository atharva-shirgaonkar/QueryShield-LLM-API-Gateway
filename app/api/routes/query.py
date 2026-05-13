"""OpenAI proxy API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from openai import AsyncOpenAI, AuthenticationError, OpenAIError

from app.core.config import settings
from app.dependencies import get_current_user
from app.models import User
from app.schemas.query import QueryRequest, QueryResponse


router = APIRouter()
client = AsyncOpenAI(api_key=settings.openai_api_key)
OPENAI_MODEL = "gpt-3.5-turbo"


@router.post("", response_model=QueryResponse)
async def query_openai(
    payload: QueryRequest,
    current_user: User = Depends(get_current_user),
) -> QueryResponse:
    try:
        completion = await client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": payload.prompt}],
        )
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenAI request failed: authentication failed with the configured API key",
        ) from exc
    except OpenAIError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenAI request failed: {exc.__class__.__name__}",
        ) from exc

    reply = completion.choices[0].message.content or ""
    return QueryResponse(response=reply, model=completion.model or OPENAI_MODEL)
