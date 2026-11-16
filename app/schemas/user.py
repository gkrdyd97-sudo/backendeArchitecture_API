import re
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel


class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(min_length=2, max_length=30, examples=["hong"])
    password: str = Field(min_length=8, max_length=64, examples=["secret1234"])

    @field_validator("username")
    @classmethod
    def check_username(cls, v: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_가-힣]+", v):
            raise ValueError("이름은 한글, 영문, 숫자, _만 사용할 수 있습니다.")
        return v

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        if not (re.search(r"[A-Za-z]", v) and re.search(r"\d", v)):
            raise ValueError("비밀번호는 영문과 숫자를 모두 포함해야 합니다.")
        return v


class UserRead(ORMModel):
    id: int
    email: EmailStr
    username: str
    role: str
    created_at: datetime


class UserBrief(ORMModel):
    id: int
    username: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="만료까지 남은 초")
