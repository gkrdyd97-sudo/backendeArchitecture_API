"""비밀번호 해싱과 JWT 발급·검증."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError


def hash_password(password: str) -> str:
    # bcrypt: 매번 다른 salt를 붙이고 일부러 느리게 계산해 무차별 대입을 어렵게 한다
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(user_id: int) -> tuple[str, int]:
    settings = get_settings()
    expires_in = settings.access_token_expire_minutes * 60
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),           # 누구의 토큰인지
        "iat": now,                    # 발급 시각
        "exp": now + timedelta(seconds=expires_in),  # 만료 시각 → 지나면 검증 실패
        "type": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str) -> int:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],  # 알고리즘을 고정해 'none' 알고리즘 공격 차단
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("토큰이 만료되었습니다. 다시 로그인하세요.", code="TOKEN_EXPIRED")
    except jwt.InvalidTokenError:
        raise AuthenticationError("유효하지 않은 토큰입니다.", code="INVALID_TOKEN")
    if payload.get("type") != "access":
        raise AuthenticationError("유효하지 않은 토큰입니다.", code="INVALID_TOKEN")
    return int(payload["sub"])
