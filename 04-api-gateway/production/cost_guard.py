"""
Cost Guard — Bảo Vệ Budget LLM

Mục tiêu: Tránh bill bất ngờ từ LLM API.
- Đếm tokens đã dùng mỗi ngày
- Cảnh báo khi gần hết budget
- Block khi vượt budget

Trong production: lưu trong Redis/DB, không phải in-memory.
"""
import time
import logging
from dataclasses import dataclass, field
from fastapi import HTTPException
import os
import redis

logger = logging.getLogger(__name__)


# Giá token (tham khảo, thay đổi theo model)
PRICE_PER_1K_INPUT_TOKENS = 0.00015   # GPT-4o-mini: $0.15/1M input
PRICE_PER_1K_OUTPUT_TOKENS = 0.0006   # GPT-4o-mini: $0.60/1M output


@dataclass
class UsageRecord:
    user_id: str
    input_tokens: int = 0
    output_tokens: int = 0
    request_count: int = 0
    day: str = field(default_factory=lambda: time.strftime("%Y-%m-%d"))

    @property
    def total_cost_usd(self) -> float:
        input_cost = (self.input_tokens / 1000) * PRICE_PER_1K_INPUT_TOKENS
        output_cost = (self.output_tokens / 1000) * PRICE_PER_1K_OUTPUT_TOKENS
        return round(input_cost + output_cost, 6)


class CostGuard:
    def __init__(
        self,
        daily_budget_usd: float = 1.0,       # $1/ngày per user
        global_daily_budget_usd: float = 10.0, # $10/ngày tổng cộng
        warn_at_pct: float = 0.8,              # Cảnh báo khi dùng 80%
    ):
        self.daily_budget_usd = daily_budget_usd
        self.global_daily_budget_usd = global_daily_budget_usd
        self.warn_at_pct = warn_at_pct
        # self._records: dict[str, UsageRecord] = {}
        # self._global_today = time.strftime("%Y-%m-%d")
        # self._global_cost = 0.0
        self.redis = redis.Redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
        )
        self._global_today = time.strftime("%Y-%m-%d")

    def _get_record(self, user_id: str) -> UsageRecord:
        today = time.strftime("%Y-%m-%d")
        key = f"cost_guard:{user_id}:{today}"
        data = self.redis.hgetall(key)

        if not data:
            record = UsageRecord(user_id=user_id, day=today)
            self.redis.hset(
                key,
                mapping={
                    "user_id": record.user_id,
                    "input_tokens": record.input_tokens,
                    "output_tokens": record.output_tokens,
                    "request_count": record.request_count,
                    "day": record.day,
                },
            )
            self.redis.expire(key, 2 * 24 * 3600)
            return record

        return UsageRecord(
            user_id=data["user_id"],
            input_tokens=int(data["input_tokens"]),
            output_tokens=int(data["output_tokens"]),
            request_count=int(data["request_count"]),
            day=data["day"],
        )

    def check_budget(self, user_id: str) -> None:
        """
        Kiểm tra budget trước khi gọi LLM.
        Raise 402 nếu vượt budget.
        """
        record = self._get_record(user_id)

        # Global budget check
        today = time.strftime("%Y-%m-%d")
        global_key = f"cost_guard:global:{today}"
        global_cost = float(self.redis.get(global_key) or 0.0)

        if global_cost >= self.global_daily_budget_usd:
            logger.critical(f"GLOBAL BUDGET EXCEEDED: ${global_cost:.4f}")
            raise HTTPException(
                status_code=503,
                detail="Service temporarily unavailable due to budget limits. Try again tomorrow.",
            )

        # Per-user budget check
        if record.total_cost_usd >= self.daily_budget_usd:
            raise HTTPException(
                status_code=402,  # Payment Required
                detail={
                    "error": "Daily budget exceeded",
                    "used_usd": record.total_cost_usd,
                    "budget_usd": self.daily_budget_usd,
                    "resets_at": "midnight UTC",
                },
            )

        # Warning khi gần hết budget
        if record.total_cost_usd >= self.daily_budget_usd * self.warn_at_pct:
            logger.warning(
                f"User {user_id} at {record.total_cost_usd/self.daily_budget_usd*100:.0f}% budget"
            )

    def record_usage(
        self, user_id: str, input_tokens: int, output_tokens: int
    ) -> UsageRecord:
        """Ghi nhận usage sau khi gọi LLM xong."""
        record = self._get_record(user_id)
        record.input_tokens += input_tokens
        record.output_tokens += output_tokens
        record.request_count += 1

        today = time.strftime("%Y-%m-%d")
        user_key = f"cost_guard:{user_id}:{today}"
        self.redis.hset(
            user_key,
            mapping={
                "user_id": record.user_id,
                "input_tokens": record.input_tokens,
                "output_tokens": record.output_tokens,
                "request_count": record.request_count,
                "day": record.day,
            },
        )
        self.redis.expire(user_key, 2 * 24 * 3600)

        cost = (
            input_tokens / 1000 * PRICE_PER_1K_INPUT_TOKENS
            + output_tokens / 1000 * PRICE_PER_1K_OUTPUT_TOKENS
        )

        global_key = f"cost_guard:global:{today}"
        self.redis.incrbyfloat(global_key, cost)
        self.redis.expire(global_key, 2 * 24 * 3600)

        logger.info(
            f"Usage: user={user_id} req={record.request_count} "
            f"cost=${record.total_cost_usd:.4f}/{self.daily_budget_usd}"
        )
        return record

    def get_usage(self, user_id: str) -> dict:
        record = self._get_record(user_id)
        return {
            "user_id": user_id,
            "date": record.day,
            "requests": record.request_count,
            "input_tokens": record.input_tokens,
            "output_tokens": record.output_tokens,
            "cost_usd": record.total_cost_usd,
            "budget_usd": self.daily_budget_usd,
            "budget_remaining_usd": max(0, self.daily_budget_usd - record.total_cost_usd),
            "budget_used_pct": round(record.total_cost_usd / self.daily_budget_usd * 100, 1),
        }


# Singleton
cost_guard = CostGuard(daily_budget_usd=1.0, global_daily_budget_usd=10.0)
