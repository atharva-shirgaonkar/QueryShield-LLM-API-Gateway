"""OpenAI proxy API routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from openai import AsyncOpenAI, AuthenticationError, OpenAIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.token_counter import count_tokens
from app.core.usage_service import get_total_tokens_used, has_exceeded_limit
from app.dependencies import get_current_user
from app.models import Usage, User
from app.schemas.query import QueryRequest, QueryResponse


router = APIRouter()
client = AsyncOpenAI(api_key=settings.openai_api_key)
OPENAI_MODEL = "gpt-3.5-turbo"


@router.post("", response_model=QueryResponse)
async def query_openai(
    payload: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QueryResponse:
    total_used = await get_total_tokens_used(current_user.id, db)
    if has_exceeded_limit(current_user, total_used, settings):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Token limit reached for your tier. Please upgrade to pro.",
        )

    prompt_tokens = count_tokens(payload.prompt, OPENAI_MODEL)

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
    model = completion.model or OPENAI_MODEL
    completion_tokens = count_tokens(reply, model)
    total_tokens = prompt_tokens + completion_tokens

    if completion.usage is not None:
        prompt_tokens = completion.usage.prompt_tokens
        completion_tokens = completion.usage.completion_tokens
        total_tokens = completion.usage.total_tokens

    usage = Usage(
        user_id=current_user.id,
        prompt=payload.prompt,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        model=model,
    )
    db.add(usage)
    await db.commit()

    return QueryResponse(
        response=reply,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
    )
