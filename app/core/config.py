from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경 변수(.env)에서 읽는 설정. 비밀값은 코드에 넣지 않는다."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Board API"
    database_url: str = "postgresql+asyncpg://board:board@localhost:5432/board"

    jwt_secret_key: str  # 필수: openssl rand -hex 32 로 생성
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    upload_dir: str = "uploads"
    max_upload_bytes: int = 5 * 1024 * 1024  # 5MB
    allowed_upload_types: tuple[str, ...] = ("image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf")

    cache_ttl_seconds: int = 30
    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
