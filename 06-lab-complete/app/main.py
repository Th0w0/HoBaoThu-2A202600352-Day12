import json
import time
import logging
import signal
import sys
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request
from pydantic import BaseModel, Field
import redis

from .config import settings
from .auth import verify_api_key
from .rate_limiter import check_rate_limit
from .cost_guard import check_budget
# =========================
# Logging (structured)
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

START_TIME = time.time()
redis_client = None


# =========================
# Graceful shutdown
# =========================
def shutdown_handler(signum, frame):
    logger.info(json.dumps({
        "event": "shutdown",
        "signal": signum,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }))
    sys.exit(0)


signal.signal(signal.SIGTERM, shutdown_handler)


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

        logger.info(json.dumps({
            "event": "startup",
            "redis": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }))

    except Exception as e:
        logger.exception("Redis connection failed: %s", e)
        redis_client = None

    yield

    logger.info(json.dumps({
        "event": "graceful_shutdown",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }))

    if redis_client:
        redis_client.close()


# =========================
# App init
# =========================
app = FastAPI(
    title="Production AI Agent",
    version="final",
    lifespan=lifespan,
)


# =========================
# Models
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
# Redis helpers
# =========================
def get_redis():
    if redis_client is None:
        raise HTTPException(status_code=503, detail="Redis not available")
    return redis_client


def conversation_key(user_id: str):
    return f"conversation:{user_id}"


def load_history(user_id: str):
    r = get_redis()
    raw = r.lrange(conversation_key(user_id), 0, -1)
    return [json.loads(x) for x in raw if x]


def save_message(user_id: str, role: str, content: str):
    r = get_redis()
    payload = {
        "role": role,
        "content": content,
        "ts": datetime.now(timezone.utc).isoformat()
    }
    r.rpush(conversation_key(user_id), json.dumps(payload))
    r.expire(conversation_key(user_id), 86400)


# =========================
# Mock LLM
# =========================
def generate_answer(question, history):
    q = question.lower().strip()

    if q == "what did i just say?":
        prev = [m["content"] for m in history if m["role"] == "user"]
        return f'You just said: "{prev[-1]}"' if prev else "No history yet."

    if q in {"hello", "hi"}:
        return "Hello! How can I help you?"

    return f"You asked: {question}"


# =========================
# Endpoints
# =========================
@app.get("/health")
def health():
    return {
        "status": "ok",
        "uptime": round(time.time() - START_TIME, 1),
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/ready")
def ready():
    try:
        r = get_redis()
        r.ping()
        return {"status": "ready"}
    except:
        raise HTTPException(503, "Not ready")


@app.post("/ask", response_model=AskResponse)
def ask(
    body: AskRequest,
    request: Request,
    _auth: str = Depends(verify_api_key),
):
    try:
        # ✅ Rate limit theo user_id
        rate_info = check_rate_limit(body.user_id)

        # ✅ Budget guard
        check_budget(body.user_id)

        # History
        history = load_history(body.user_id)

        # LLM
        answer = generate_answer(body.question, history)

        # Save
        save_message(body.user_id, "user", body.question)
        save_message(body.user_id, "assistant", answer)

        logger.info(json.dumps({
            "event": "request",
            "user_id": body.user_id,
            "remaining": rate_info["remaining"],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }))

        return AskResponse(
            user_id=body.user_id,
            question=body.question,
            answer=answer,
            timestamp=datetime.now(timezone.utc).isoformat(),
            history_count=len(history) + 2
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Internal error: %s", e)
        raise HTTPException(500, "Internal server error")