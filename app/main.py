import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.api.routers import auth, posts
from app.core.cache import TTLCache
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.middleware import RequestContextMiddleware
from app.db.models import Base
from app.db.session import engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작할 때: 테이블이 없으면 만든다 (운영이 커지면 Alembic 마이그레이션으로 교체)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # 종료할 때: DB 연결 풀 정리
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description=(
        "JWT 인증 게시판 REST API\n\n"
        "1. `POST /api/v1/auth/signup`으로 가입\n"
        "2. 오른쪽 위 **Authorize** 버튼 → username에 이메일, password 입력\n"
        "3. 자물쇠 표시가 있는 API를 로그인한 상태로 호출"
    ),
    lifespan=lifespan,
)

app.state.cache = TTLCache(settings.cache_ttl_seconds)

# 미들웨어: 아래에 쓴 것이 바깥쪽에서 먼저 실행된다
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time-Ms", "X-Cache"],
)

register_exception_handlers(app)
app.include_router(auth.router)
app.include_router(posts.router)

Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


@app.get("/health", tags=["system"], summary="서버·DB 상태 확인")
async def health():
    async with engine.connect() as conn:
        await conn.execute(text("select 1"))
    return {"status": "ok", "database": "ok"}
