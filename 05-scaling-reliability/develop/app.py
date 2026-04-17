"""
BASIC — Health Check + Graceful Shutdown

Hai tính năng tối thiểu cần có trước khi deploy:
  1. GET /health  — liveness: "agent có còn sống không?"
  2. GET /ready   — readiness: "agent có sẵn sàng nhận request chưa?"
  3. Graceful shutdown: hoàn thành request hiện tại trước khi tắt

Chạy:
    python app.py

Test health check:
    curl http://localhost:8000/health
    curl http://localhost:8000/ready

Simulate shutdown:
    # Trong terminal khác
    kill -SIGTERM <pid>
    # Xem agent log graceful shutdown message
"""
import os
import time
import signal
import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
import redis
import sqlite3
from fastapi.responses import JSONResponse
from fastapi import FastAPI, HTTPException
import uvicorn
from utils.mock_llm import ask

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

START_TIME = time.time()
_is_ready = False
_in_flight_requests = 0  # đếm số request đang xử lý

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

DB_PATH = os.getenv("DB_PATH", "app.db")
db = sqlite3.connect(DB_PATH, check_same_thread=False)
_shutting_down = False

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready

    # ── Startup ──
    logger.info("Agent starting up...")
    logger.info("Loading model and checking dependencies...")
    time.sleep(0.2)  # simulate startup time
    _is_ready = True
    logger.info("✅ Agent is ready!")

    yield

    # ── Shutdown ──
    global _shutting_down
    _is_ready = False
    _shutting_down = True
    logger.info("🔄 Graceful shutdown initiated...")

    timeout = 30
    elapsed = 0
    while _in_flight_requests > 0 and elapsed < timeout:
        logger.info(f"Waiting for {_in_flight_requests} in-flight requests...")
        time.sleep(1)
        elapsed += 1

    logger.info("✅ Shutdown complete")



app = FastAPI(title="Agent — Health Check Demo", lifespan=lifespan)

@app.middleware("http")
async def track_requests(request, call_next):
    global _in_flight_requests

    if _shutting_down and request.url.path not in ["/health"]:
        raise HTTPException(status_code=503, detail="Server is shutting down")

    _in_flight_requests += 1
    try:
        response = await call_next(request)
        return response
    finally:
        _in_flight_requests -= 1


# ──────────────────────────────────────────────────────────
# Business Logic
# ──────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"message": "AI Agent with health checks!"}


@app.post("/ask")
async def ask_agent(question: str):
    if not _is_ready:
        raise HTTPException(503, "Agent not ready")
    return {"answer": ask(question)}


# ──────────────────────────────────────────────────────────
# HEALTH CHECKS — Phần quan trọng nhất của file này
# ──────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

@app.get("/ready")
def ready():
    if not _is_ready:
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "reason": "app is starting or shutting down"},
        )

    try:
        redis_client.ping()
        db.execute("SELECT 1")
        return {
            "status": "ready",
            "in_flight_requests": _in_flight_requests,
        }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "not ready",
                "error": str(e),
            },
        )


# ──────────────────────────────────────────────────────────
# GRACEFUL SHUTDOWN
# ──────────────────────────────────────────────────────────

def handle_sigterm(signum, frame):
    signal_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT"
    logger.info(f"Received {signal_name} — starting graceful shutdown")


signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting agent on port {port}")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        # ✅ Cho phép graceful shutdown
        timeout_graceful_shutdown=30,
    )
