import os
import tempfile

# 앱을 불러오기 전에 테스트용 설정을 넣는다
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://board:board@localhost:5432/board_test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only-0123456789")
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp()

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.db.models import Base  # noqa: E402
from app.db.session import engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest.fixture
async def client():
    app.state.cache.clear()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def signup_and_login(client: AsyncClient, name: str) -> dict:
    email = f"{name}@example.com"
    await client.post("/api/v1/auth/signup", json={"email": email, "username": name, "password": "password123"})
    res = await client.post("/api/v1/auth/login", data={"username": email, "password": "password123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}
