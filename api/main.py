import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pathlib import Path

# Load .env from project root
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from api.auth.middleware import IPRateLimitMiddleware
from api.auth.router import router as auth_router
from api.routers.logs import router as logs_router
from api.routers.stats import router as stats_router
from api.routers.pipeline_runs import router as pipeline_runs_router
from api.routers.users import router as users_router
from api.dependencies import get_db_engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: DB 연결 미리 확인
    engine = get_db_engine()
    try:
        with engine.connect():
            pass
    except Exception as e:
        print(f"❌ DB connection failed on startup: {e}")
    yield
    # shutdown: 커넥션 풀 정리
    engine.dispose()

app = FastAPI(title="KiloStone API", version="1.0.0", lifespan=lifespan)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("FRONTEND_URL", "http://localhost:3000")],
    allow_credentials=True,   # 쿠키 전달 허용 (refresh token)
    allow_methods=["*"],
    allow_headers=["*"],
)

# IP 차단 미들웨어
app.add_middleware(IPRateLimitMiddleware)

# 라우터 등록
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(logs_router)
app.include_router(stats_router)
app.include_router(pipeline_runs_router)

@app.get("/health")
def health():
    return {"status": "ok"}
