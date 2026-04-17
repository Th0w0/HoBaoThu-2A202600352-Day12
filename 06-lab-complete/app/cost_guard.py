import redis
from fastapi import HTTPException
from config import settings

redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

def check_budget():
    try:
        # bản đơn giản: chỉ check tổng cost global
        key = "budget:monthly"
        current = redis_client.get(key)
        current_value = float(current) if current else 0.0

        if current_value >= settings.monthly_budget_usd:
            raise HTTPException(status_code=429, detail="Monthly budget exceeded")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Budget guard unavailable")