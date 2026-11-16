from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_, select

from app.api.deps import CurrentUser, DbSession
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User
from app.schemas.common import ErrorResponse
from app.schemas.user import Token, UserCreate, UserRead

router = APIRouter(prefix="/api/v1", tags=["auth"])


@router.post(
    "/auth/signup",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="회원가입",
    responses={409: {"model": ErrorResponse, "description": "이메일 또는 이름 중복"}},
)
async def signup(body: UserCreate, db: DbSession):
    exists = await db.scalar(select(User).where(or_(User.email == body.email, User.username == body.username)))
    if exists:
        field = "email" if exists.email == body.email else "username"
        raise ConflictError(f"이미 사용 중인 {'이메일' if field == 'email' else '이름'}입니다.", code="DUPLICATE_" + field.upper())
    user = User(email=body.email, username=body.username, hashed_password=hash_password(body.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post(
    "/auth/login",
    response_model=Token,
    summary="로그인 (JWT 발급)",
    description="username 칸에 **이메일**을 넣습니다. Swagger의 Authorize 버튼도 이 API를 씁니다.",
    responses={401: {"model": ErrorResponse}},
)
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession):
    user = await db.scalar(select(User).where(User.email == form.username))
    # 이메일이 없는 경우와 비밀번호가 틀린 경우를 같은 메시지로 → 가입 여부 노출 방지
    if user is None or not verify_password(form.password, user.hashed_password):
        raise AuthenticationError("이메일 또는 비밀번호가 올바르지 않습니다.", code="INVALID_CREDENTIALS")
    token, expires_in = create_access_token(user.id)
    return Token(access_token=token, expires_in=expires_in)


@router.get("/users/me", response_model=UserRead, summary="내 정보", tags=["users"],
            responses={401: {"model": ErrorResponse}})
async def me(user: CurrentUser):
    return user
