FROM python:3.12-slim

# uv 바이너리만 복사해서 사용 (버전 고정)
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

# 의존성 먼저 설치 → 코드만 바뀌면 이 층은 캐시 재사용
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
RUN useradd --create-home appuser && mkdir -p /app/uploads && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
