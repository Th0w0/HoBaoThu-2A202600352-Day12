import time
import redis
from fastapi import HTTPException
import os

redis_client = redis.Redis.from_url(
    os.getenv("REDIS_URL", "redis://redis:6379/0"),
    decode_responses=True
)


def check_rate_limit(user_id: str, limit: int = 10):
    try:
        bucket = f"rate_limit:{user_id}:{int(time.time() // 60)}"

        count = redis_client.incr(bucket)

        if count == 1:
            redis_client.expire(bucket, 60)

        if count > limit:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": "60"},
            )

        return {
            "limit": limit,
            "remaining": max(0, limit - count)
        }

    except HTTPException:
        raise
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Rate limiter unavailable")