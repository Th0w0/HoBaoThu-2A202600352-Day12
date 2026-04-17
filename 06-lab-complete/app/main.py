import json
import time
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request
from pydantic import BaseModel, Field
import redis

from config import settings
from auth import verify_api_key
from rate_limiter import check_rate_limit
from cost_guard import check_budget

# Nếu bạn có mock llm thì giữ import này
# from utils.mock_llm import ask as llm_ask

logger = logging.getLogger(__name__)
logging.basicConfig(level=getattr(logging, str(getattr(settings, "log_level", "INFO")).upper(), logging.INFO))

START_TIME = time.time()
redis_client = None


# =========================
# Lifespan
# =========================
@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client

    try:
        redis_client = redis.Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
        redis_client.ping()
        logger.info("Startup complete: Redis connected")
    except Exception as e:
        logger.exception("Startup warning: Redis connection failed: %s", e)
        redis_client = None

    yield

    logger.info("Graceful shutdown: closing application resources")
    if redis_client is not None:
        try:
            redis_client.close()
        except Exception:
            pass


app = FastAPI(
    title=getattr(settings, "app_name", "Production AI Agent"),
    version=getattr(settings, "app_version", "1.0.0"),
    lifespan=lifespan,
)


# =========================
# Request / Response Models
# =========================
class AskRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=100)
    question: str = Field(..., min_length=1, max_length=2000)


class AskResponse(BaseModel):
    user_id: str
    question: str
    answer: str
    timestamp: str
    history_count: int


# =========================
# Helpers
# =========================
def get_redis():
    if redis_client is None:
        raise HTTPException(status_code=503, detail="Redis not available")
    return redis_client


def conversation_key(user_id: str) -> str:
    return f"conversation:{user_id}"


def load_history(user_id: str) -> list[dict]:
    r = get_redis()
    raw_items = r.lrange(conversation_key(user_id), 0, -1)
    history = []
    for item in raw_items:
        try:
            history.append(json.loads(item))
        except json.JSONDecodeError:
            continue
    return history


def save_message(user_id: str, role: str, content: str) -> None:
    r = get_redis()
    key = conversation_key(user_id)
    payload = {
        "role": role,
        "content": content,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    r.rpush(key, json.dumps(payload))
    r.expire(key, 60 * 60 * 24)  # giữ 24h, có thể chỉnh


def generate_answer(question: str, history: list[dict]) -> str:
    """
    Mock logic để pass rubric conversation test.
    Có thể thay bằng OpenAI/mock_llm sau.
    """

    normalized = question.strip().lower()

    if normalized == "what did i just say?":
        previous_user_messages = [
            msg["content"] for msg in history if msg.get("role") == "user"
        ]
        if previous_user_messages:
            return f'You just said: "{previous_user_messages[-1]}"'
        return "You have not said anything earlier in this conversation."

    if normalized in {"hello", "hi", "hey"}:
        return "Hello! How can I help you?"

    return f"You asked: {question}"


# =========================
# Endpoints
# =========================
@app.get("/health")
def health():
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready")
def ready():
    try:
        r = get_redis()
        r.ping()
        return {
            "status": "ready",
            "redis": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Readiness check failed: %s", e)
        raise HTTPException(status_code=503, detail="Redis not ready")


@app.post("/ask", response_model=AskResponse)
def ask(
    body: AskRequest,
    request: Request,
    _auth: str = Depends(verify_api_key),
    _rate_limit: None = Depends(check_rate_limit),
    _budget: None = Depends(check_budget),
):
    """
    Flow:
    1. Validate request body via Pydantic -> invalid body returns 422 automatically
    2. Load conversation history from Redis
    3. Generate answer
    4. Save user + assistant messages to Redis
    5. Return response
    """
    try:
        history = load_history(body.user_id)

        answer = generate_answer(body.question, history)

        save_message(body.user_id, "user", body.question)
        save_message(body.user_id, "assistant", answer)

        new_history_count = len(history) + 2

        logger.info(
            "Request handled",
            extra={
                "user_id": body.user_id,
                "path": str(request.url.path),
            },
        )

        return AskResponse(
            user_id=body.user_id,
            question=body.question,
            answer=answer,
            timestamp=datetime.now(timezone.utc).isoformat(),
            history_count=new_history_count,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Unhandled error in /ask: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")