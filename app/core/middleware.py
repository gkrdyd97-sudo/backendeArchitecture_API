"""요청마다 ID를 붙이고 처리 시간을 기록하는 미들웨어."""
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("board.access")


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        start = time.perf_counter()

        response = await call_next(request)

        elapsed_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id          # 오류 문의 시 로그를 찾는 열쇠
        response.headers["X-Process-Time-Ms"] = f"{elapsed_ms:.1f}"
        logger.info("%s %s %s %.1fms id=%s", request.method, request.url.path, response.status_code, elapsed_ms, request_id)
        return response
