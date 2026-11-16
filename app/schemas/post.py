from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import ORMModel
from app.schemas.user import UserBrief


def _not_blank(v: str | None) -> str | None:
    if v is not None and not v.strip():
        raise ValueError("공백만 입력할 수 없습니다.")
    return v.strip() if v is not None else v


class PostCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200, examples=["첫 게시글"])
    content: str = Field(min_length=1, max_length=20000, examples=["안녕하세요"])

    _strip = field_validator("title", "content")(_not_blank)


class PostUpdate(BaseModel):
    """PATCH: 보낸 필드만 수정"""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    content: str | None = Field(default=None, min_length=1, max_length=20000)

    _strip = field_validator("title", "content")(_not_blank)

    @model_validator(mode="after")
    def at_least_one(self):
        if self.title is None and self.content is None:
            raise ValueError("수정할 필드를 하나 이상 보내세요.")
        return self


class CommentCreate(BaseModel):
    content: str = Field(min_length=1, max_length=1000)

    _strip = field_validator("content")(_not_blank)


class CommentRead(ORMModel):
    id: int
    content: str
    author: UserBrief
    created_at: datetime


class AttachmentRead(ORMModel):
    id: int
    original_name: str
    content_type: str
    size: int
    url: str


class PostSummary(ORMModel):
    id: int
    title: str
    author: UserBrief
    view_count: int
    comment_count: int
    created_at: datetime


class PostRead(ORMModel):
    id: int
    title: str
    content: str
    author: UserBrief
    view_count: int
    created_at: datetime
    updated_at: datetime
    comments: list[CommentRead]
    attachments: list[AttachmentRead]
