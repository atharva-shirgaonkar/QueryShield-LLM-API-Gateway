"""OpenAI proxy API routes."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI, AuthenticationError, OpenAIError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import get_cache_key, get_cached_response, set_cached_response
from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from app.core.config import settings
from app.core.database import get_db
from app.core.logger import get_logger
from app.core.rate_limiter import (
    RATE_LIMIT_WINDOW,
    check_rate_limit,
    get_rate_limit_key,
)
from app.core.redis_client import get_redis
from app.core.semantic_cache import find_semantic_match, store_semantic_cache
from app.core.token_counter import count_tokens
from app.core.usage_service import get_total_tokens_used, has_exceeded_limit
from app.dependencies import get_current_user
from app.models import Usage, User
from app.schemas.query import QueryRequest, QueryResponse


router = APIRouter()
logger = get_logger(__name__)
client = AsyncOpenAI(api_key=settings.openai_api_key)
openai_circuit_breaker = CircuitBreaker()
OPENAI_MODEL = "gpt-3.5-turbo"


def _state_value(state) -> str:
    return state.value if hasattr(state, "value") else str(state)


def _tier_value(current_user: User) -> str:
    return (
        current_user.tier.value
        if hasattr(current_user.tier, "value")
        else str(current_user.tier)
    )


def _remaining_requests(current_count: int, limit: int) -> int:
    return max(limit - current_count, 0)


def _set_rate_limit_headers(
    response: Response,
    *,
    limit: int,
    remaining: int,
    reset: int,
) -> None:
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(reset)


async def _get_rate_limit_reset(user_id: int, redis) -> int:
    ttl = await redis.ttl(get_rate_limit_key(user_id))
    if ttl is None or ttl < 0:
        return RATE_LIMIT_WINDOW
    return int(ttl)


def _log_circuit_breaker_state_change(
    *,
    request: Request,
    previous_state,
    user_id: int,
    tier: str,
) -> None:
    current_state = openai_circuit_breaker.state
    if current_state == previous_state:
        return

    logger.warning(
        "Circuit breaker state changed",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "user_id": user_id,
            "tier": tier,
            "previous_state": _state_value(previous_state),
            "current_state": _state_value(current_state),
        },
    )


@router.post("", response_model=QueryResponse)
async def query_openai(
    request: Request,
    http_response: Response,
    payload: QueryRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    redis: Redis = Depends(get_redis),
) -> QueryResponse | JSONResponse:
    tier = _tier_value(current_user)
    request.state.user_id = current_user.id

    is_allowed, current_count, limit = await check_rate_limit(current_user, redis)
    rate_limit_remaining = _remaining_requests(current_count, limit)
    rate_limit_reset = await _get_rate_limit_reset(current_user.id, redis)
    _set_rate_limit_headers(
        http_response,
        limit=limit,
        remaining=rate_limit_remaining,
        reset=rate_limit_reset,
    )

    if not is_allowed:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "detail": "Rate limit exceeded. Try again in 60 seconds.",
                "retry_after": RATE_LIMIT_WINDOW,
            },
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": str(rate_limit_remaining),
                "X-RateLimit-Reset": str(rate_limit_reset),
            },
        )

    logger.info(
        "Query request received",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "user_id": current_user.id,
            "tier": tier,
        },
    )

    total_used = await get_total_tokens_used(current_user.id, db)
    if has_exceeded_limit(current_user, total_used, settings):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Token limit reached for your tier. Please upgrade to pro.",
        )

    cache_key = get_cache_key(payload.prompt)
    cached_response = await get_cached_response(cache_key, redis)
    if cached_response is not None:
        request.state.cached = True
        request.state.token_count = cached_response["total_tokens"]

        logger.info(
            "Cache hit",
            extra={
                "request_id": getattr(request.state, "request_id", None),
                "user_id": current_user.id,
                "tier": tier,
                "cache_key": cache_key,
            },
        )

        usage = Usage(
            user_id=current_user.id,
            prompt=payload.prompt,
            prompt_tokens=cached_response["prompt_tokens"],
            completion_tokens=cached_response["completion_tokens"],
            total_tokens=cached_response["total_tokens"],
            model=cached_response["model"],
            cached=True,
        )
        db.add(usage)
        await db.commit()

        cached_response["cached"] = True
        cached_response["semantic_cached"] = False
        cached_response["rate_limit_remaining"] = rate_limit_remaining
        return QueryResponse(**cached_response)

    logger.info(
        "Cache miss",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "user_id": current_user.id,
            "tier": tier,
            "cache_key": cache_key,
        },
    )

    semantic_response = await find_semantic_match(payload.prompt, redis)
    if semantic_response is not None:
        request.state.cached = True
        request.state.token_count = semantic_response["total_tokens"]

        logger.info(
            "Semantic cache hit",
            extra={
                "request_id": getattr(request.state, "request_id", None),
                "user_id": current_user.id,
                "tier": tier,
            },
        )

        usage = Usage(
            user_id=current_user.id,
            prompt=payload.prompt,
            prompt_tokens=semantic_response["prompt_tokens"],
            completion_tokens=semantic_response["completion_tokens"],
            total_tokens=semantic_response["total_tokens"],
            model=semantic_response["model"],
            cached=True,
        )
        db.add(usage)
        await db.commit()

        semantic_response["cached"] = False
        semantic_response["semantic_cached"] = True
        semantic_response["rate_limit_remaining"] = rate_limit_remaining
        return QueryResponse(**semantic_response)

    logger.info(
        "Semantic cache miss",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "user_id": current_user.id,
            "tier": tier,
        },
    )

    prompt_tokens = count_tokens(payload.prompt, OPENAI_MODEL)
    previous_state = openai_circuit_breaker.state

    try:
        completion = await openai_circuit_breaker.call(
            client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": payload.prompt}],
            )
        )
    except CircuitBreakerOpenError as exc:
        logger.warning(
            "Circuit breaker blocked request",
            extra={
                "request_id": getattr(request.state, "request_id", None),
                "user_id": current_user.id,
                "tier": tier,
                "current_state": _state_value(openai_circuit_breaker.state),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable. Please try again shortly.",
        ) from exc
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
    finally:
        _log_circuit_breaker_state_change(
            request=request,
            previous_state=previous_state,
            user_id=current_user.id,
            tier=tier,
        )

    reply = completion.choices[0].message.content or ""
    model = completion.model or OPENAI_MODEL
    completion_tokens = count_tokens(reply, model)
    total_tokens = prompt_tokens + completion_tokens

    if completion.usage is not None:
        prompt_tokens = completion.usage.prompt_tokens
        completion_tokens = completion.usage.completion_tokens
        total_tokens = completion.usage.total_tokens

    request.state.cached = False
    request.state.token_count = total_tokens

    logger.info(
        "OpenAI token counts recorded",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "user_id": current_user.id,
            "tier": tier,
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
    )

    usage = Usage(
        user_id=current_user.id,
        prompt=payload.prompt,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        model=model,
        cached=False,
    )
    db.add(usage)
    await db.commit()

    response = QueryResponse(
        response=reply,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cached=False,
        semantic_cached=False,
        rate_limit_remaining=rate_limit_remaining,
    )
    cache_payload = response.model_dump(
        exclude={"cached", "semantic_cached", "rate_limit_remaining"}
    )
    await set_cached_response(cache_key, cache_payload, redis)
    await store_semantic_cache(payload.prompt, cache_payload, redis)

    return response
