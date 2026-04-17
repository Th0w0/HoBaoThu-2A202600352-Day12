import time
import redis
from fastapi import HTTPException, Request
from config import settings

redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

def check_rate_limit(request: Request):
    try:
        body = {}
        # dependency sync không đọc body tiện được, nên có thể limit theo client IP hoặc API key
        api_key = request.headers.get("X-API-Key", "anonymous")
        bucket = f"rate_limit:{api_key[:8]}:{int(time.time() // 60)}"

        count = redis_client.incr(bucket)
        if count == 1:
            redis_client.expire(bucket, 60)

        if count > settings.rate_limit_per_minute:
            raise HTTPException(status_code=429, detail="Rate limit exceeded")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Rate limiter unavailable")