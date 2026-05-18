"""Redis-backed per-user rate limiting."""

from app.models import User, UserTier


RATE_LIMIT_FREE = 10
RATE_LIMIT_PRO = 60
RATE_LIMIT_WINDOW = 60


def get_rate_limit_key(user_id: int) -> str:
    """Return the Redis key for a user's rate limit window."""
    return f"rate_limit:{user_id}"


def _get_user_limit(user: User) -> int:
    return RATE_LIMIT_PRO if user.tier == UserTier.PRO else RATE_LIMIT_FREE


async def check_rate_limit(user: User, redis) -> tuple[bool, int, int]:
    """Increment and evaluate a user's current request count."""
    limit = _get_user_limit(user)
    key = get_rate_limit_key(user.id)
    current_count = int(await redis.incr(key))

    if current_count == 1:
        await redis.expire(key, RATE_LIMIT_WINDOW)

    return current_count <= limit, current_count, limit
