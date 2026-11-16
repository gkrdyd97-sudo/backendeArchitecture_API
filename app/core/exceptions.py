"""일관된 오류 응답.

모든 오류는 아래 모양으로 응답한다.
{
  "error": { "code": "POST_NOT_FOUND", "message": "게시글을 찾을 수 없습니다.", "details": null },
  "request_id": "6f1c…"
}
"""
import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("board")


class AppError(Exception):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "BAD_REQUEST"
    message = "잘못된 요청입니다."

    def __init__(self, message: str | None = None, *, code: str | None = None, details: object = None):
        self.message = message or self.message
        self.code = code or self.code
        self.details = details
        super().__init__(self.message)


class NotFoundError(AppError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "NOT_FOUND"
    message = "대상을 찾을 수 없습니다."


class ConflictError(AppError):
    status_code = status.HTTP_409_CONFLICT
    code = "CONFLICT"
    message = "이미 존재합니다."


class AuthenticationError(AppError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "UNAUTHORIZED"
    message = "로그인이 필요합니다."


class PermissionDeniedError(AppError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "FORBIDDEN"
    message = "권한이 없습니다."


class PayloadTooLargeError(AppError):
    status_code = status.HTTP_413_CONTENT_TOO_LARGE
    code = "FILE_TOO_LARGE"
    message = "파일이 너무 큽니다."


def _body(request: Request, code: str, message: str, details: object = None) -> dict:
    return {
        "error": {"code": code, "message": message, "details": details},
        "request_id": getattr(request.state, "request_id", None),
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(_body(request, exc.code, exc.message, exc.details), status_code=exc.status_code, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        # Pydantic 기본 오류 목록을 필드·이유만 남긴 단순한 형태로 바꾼다
        details = [
            {
                "field": ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path")),
                "reason": err["msg"].removeprefix("Value error, "),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            _body(request, "VALIDATION_ERROR", "입력값을 확인하세요.", details),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(request: Request, exc: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 401: "UNAUTHORIZED"}.get(exc.status_code, "HTTP_ERROR")
        message = "요청한 주소가 없습니다." if exc.status_code == 404 else str(exc.detail)
        return JSONResponse(_body(request, code, message), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        logger.exception("처리하지 못한 오류 request_id=%s", getattr(request.state, "request_id", None))
        return JSONResponse(
            _body(request, "INTERNAL_SERVER_ERROR", "서버 오류가 발생했습니다. 잠시 후 다시 시도하세요."),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


class UnsupportedMediaTypeError(AppError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    code = "UNSUPPORTED_FILE_TYPE"
    message = "허용하지 않는 파일 형식입니다."
