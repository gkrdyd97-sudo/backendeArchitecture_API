from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

engine = create_async_engine(
    get_settings().database_url,
    pool_pre_ping=True,  # 끊긴 연결을 미리 확인 (DB 재시작 대비)
    pool_size=5,
    max_overflow=10,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """요청 하나당 세션 하나. 요청이 끝나면 자동으로 닫힌다."""
    async with SessionLocal() as session:
        yield session
