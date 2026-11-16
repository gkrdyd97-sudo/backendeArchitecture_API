from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.core.security import decode_access_token
from app.db.models import User
from app.db.session import get_db

# tokenUrl: Swagger UI의 Authorize 버튼이 이 주소로 로그인한다
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(db: DbSession, token: Annotated[str | None, Depends(oauth2_scheme)]) -> User:
    if not token:
        raise AuthenticationError()
    user = await db.get(User, decode_access_token(token))
    if user is None:
        raise AuthenticationError("탈퇴했거나 존재하지 않는 사용자입니다.", code="INVALID_TOKEN")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def ensure_owner(user: User, author_id: int, what: str = "게시글") -> None:
    """작성자 본인 또는 관리자만 통과 (인가)"""
    if user.role != "admin" and user.id != author_id:
        raise PermissionDeniedError(f"본인이 작성한 {what}만 수정·삭제할 수 있습니다.", code="NOT_AUTHOR")
