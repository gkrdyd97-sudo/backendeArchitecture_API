import math
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Query, Request, Response, UploadFile, status
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession, ensure_owner
from app.core.config import get_settings
from app.core.exceptions import AppError, NotFoundError, PayloadTooLargeError, UnsupportedMediaTypeError
from app.db.models import Attachment, Comment, Post, User
from app.schemas.common import ErrorResponse, Page
from app.schemas.post import (
    AttachmentRead,
    CommentCreate,
    CommentRead,
    PostCreate,
    PostRead,
    PostSummary,
    PostUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["posts"])

ERRORS = {
    401: {"model": ErrorResponse, "description": "로그인 필요 / 토큰 만료"},
    403: {"model": ErrorResponse, "description": "작성자가 아님"},
    404: {"model": ErrorResponse, "description": "게시글 없음"},
}


def cache_of(request: Request):
    return request.app.state.cache


async def get_post_or_404(db, post_id: int) -> Post:
    post = await db.scalar(
        select(Post)
        .where(Post.id == post_id)
        # 관계를 미리 한 번에 가져와 N+1 쿼리를 막는다 (게시글 1 + 작성자·댓글·첨부 각각 1)
        .options(
            selectinload(Post.author),
            selectinload(Post.comments).selectinload(Comment.author),
            selectinload(Post.attachments),
        )
    )
    if post is None:
        raise NotFoundError(f"게시글을 찾을 수 없습니다. (id={post_id})", code="POST_NOT_FOUND")
    return post


# ---------------------------------------------------------------- 게시글
@router.get("/posts", response_model=Page[PostSummary], summary="게시글 목록")
async def list_posts(
    request: Request,
    response: Response,
    db: DbSession,
    page: Annotated[int, Query(ge=1, description="페이지 번호")] = 1,
    size: Annotated[int, Query(ge=1, le=50, description="한 페이지 개수")] = 10,
    q: Annotated[str | None, Query(max_length=50, description="제목·내용 검색어")] = None,
    author_id: Annotated[int | None, Query(ge=1, description="작성자 id")] = None,
):
    cache = cache_of(request)
    key = f"posts:list:{page}:{size}:{q}:{author_id}"
    if (cached := cache.get(key)) is not None:
        response.headers["X-Cache"] = "HIT"
        return cached

    conditions = []
    if q:
        like = f"%{q}%"
        conditions.append(or_(Post.title.ilike(like), Post.content.ilike(like)))
    if author_id:
        conditions.append(Post.author_id == author_id)

    total = await db.scalar(select(func.count(Post.id)).where(*conditions))

    # 댓글 수는 서브쿼리로 한 번에 집계 (게시글마다 따로 세지 않음)
    comment_count = (
        select(func.count(Comment.id)).where(Comment.post_id == Post.id).correlate(Post).scalar_subquery()
    )
    rows = await db.execute(
        select(Post, comment_count.label("comment_count"))
        .where(*conditions)
        .options(selectinload(Post.author))
        .order_by(Post.created_at.desc(), Post.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    items = [
        PostSummary(
            id=p.id, title=p.title, author=p.author, view_count=p.view_count, comment_count=cnt, created_at=p.created_at
        )
        for p, cnt in rows.all()
    ]
    result = Page[PostSummary](items=items, total=total or 0, page=page, size=size, pages=math.ceil((total or 0) / size))
    cache.set(key, result)
    response.headers["X-Cache"] = "MISS"
    return result


@router.post("/posts", response_model=PostRead, status_code=status.HTTP_201_CREATED, summary="게시글 작성",
             responses={401: ERRORS[401]})
async def create_post(body: PostCreate, user: CurrentUser, db: DbSession, request: Request):
    post = Post(title=body.title, content=body.content, author_id=user.id)
    db.add(post)
    await db.commit()
    cache_of(request).invalidate_prefix("posts:")
    return await get_post_or_404(db, post.id)


@router.get("/posts/{post_id}", response_model=PostRead, summary="게시글 상세 (조회수 +1)", responses={404: ERRORS[404]})
async def read_post(post_id: int, db: DbSession):
    # 조회수는 DB에서 원자적으로 +1 → 동시에 여러 명이 봐도 빠짐없이 센다
    result = await db.execute(update(Post).where(Post.id == post_id).values(view_count=Post.view_count + 1))
    if result.rowcount == 0:
        raise NotFoundError(f"게시글을 찾을 수 없습니다. (id={post_id})", code="POST_NOT_FOUND")
    await db.commit()
    return await get_post_or_404(db, post_id)


@router.patch("/posts/{post_id}", response_model=PostRead, summary="게시글 수정 (작성자만)", responses=ERRORS)
async def update_post(post_id: int, body: PostUpdate, user: CurrentUser, db: DbSession, request: Request):
    post = await get_post_or_404(db, post_id)
    ensure_owner(user, post.author_id)
    for field, value in body.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(post, field, value)
    await db.commit()
    cache_of(request).invalidate_prefix("posts:")
    db.expire_all()
    return await get_post_or_404(db, post_id)


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT, summary="게시글 삭제 (작성자만)", responses=ERRORS)
async def delete_post(post_id: int, user: CurrentUser, db: DbSession, request: Request):
    post = await get_post_or_404(db, post_id)
    ensure_owner(user, post.author_id)
    files = [a.stored_name for a in post.attachments]
    await db.delete(post)  # 댓글·첨부 행은 cascade로 함께 삭제
    await db.commit()
    for name in files:
        (Path(get_settings().upload_dir) / name).unlink(missing_ok=True)
    cache_of(request).invalidate_prefix("posts:")


# ---------------------------------------------------------------- 댓글
@router.get("/posts/{post_id}/comments", response_model=list[CommentRead], summary="댓글 목록", tags=["comments"],
            responses={404: ERRORS[404]})
async def list_comments(post_id: int, db: DbSession):
    if await db.get(Post, post_id) is None:
        raise NotFoundError(code="POST_NOT_FOUND", message=f"게시글을 찾을 수 없습니다. (id={post_id})")
    rows = await db.scalars(
        select(Comment).where(Comment.post_id == post_id).options(selectinload(Comment.author)).order_by(Comment.id)
    )
    return rows.all()


@router.post("/posts/{post_id}/comments", response_model=CommentRead, status_code=status.HTTP_201_CREATED,
             summary="댓글 작성", tags=["comments"], responses={401: ERRORS[401], 404: ERRORS[404]})
async def create_comment(post_id: int, body: CommentCreate, user: CurrentUser, db: DbSession, request: Request):
    if await db.get(Post, post_id) is None:
        raise NotFoundError(code="POST_NOT_FOUND", message=f"게시글을 찾을 수 없습니다. (id={post_id})")
    comment = Comment(content=body.content, post_id=post_id, author_id=user.id)
    db.add(comment)
    await db.commit()
    cache_of(request).invalidate_prefix("posts:")
    return await db.scalar(select(Comment).where(Comment.id == comment.id).options(selectinload(Comment.author)))


@router.delete("/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT, summary="댓글 삭제 (작성자만)",
               tags=["comments"], responses=ERRORS)
async def delete_comment(comment_id: int, user: CurrentUser, db: DbSession, request: Request):
    comment = await db.get(Comment, comment_id)
    if comment is None:
        raise NotFoundError(f"댓글을 찾을 수 없습니다. (id={comment_id})", code="COMMENT_NOT_FOUND")
    ensure_owner(user, comment.author_id, "댓글")
    await db.delete(comment)
    await db.commit()
    cache_of(request).invalidate_prefix("posts:")


# ---------------------------------------------------------------- 첨부파일
@router.post(
    "/posts/{post_id}/attachments",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="첨부파일 업로드 (작성자만, 5MB 이하 이미지·PDF)",
    tags=["attachments"],
    responses={**ERRORS, 413: {"model": ErrorResponse}, 415: {"model": ErrorResponse}},
)
async def upload_attachment(post_id: int, user: CurrentUser, db: DbSession, request: Request,
                            file: Annotated[UploadFile, File(description="업로드할 파일")]):
    settings = get_settings()
    post = await get_post_or_404(db, post_id)
    ensure_owner(user, post.author_id)

    if file.content_type not in settings.allowed_upload_types:
        raise UnsupportedMediaTypeError(f"허용하지 않는 파일 형식입니다: {file.content_type}",
                                        details={"allowed": list(settings.allowed_upload_types)})

    # 저장 이름은 무작위로 → 경로 조작(../)과 덮어쓰기 방지
    suffix = Path(file.filename or "").suffix.lower()[:10]
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / stored_name

    # 1MB씩 비동기로 읽어 저장하며 크기 제한 확인 (큰 파일을 메모리에 통째로 올리지 않음)
    size = 0
    try:
        with target.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise PayloadTooLargeError(f"파일은 {settings.max_upload_bytes // (1024 * 1024)}MB 이하만 올릴 수 있습니다.")
                out.write(chunk)
    except AppError:
        target.unlink(missing_ok=True)
        raise

    attachment = Attachment(post_id=post_id, original_name=file.filename or stored_name, stored_name=stored_name,
                            content_type=file.content_type, size=size)
    db.add(attachment)
    await db.commit()
    cache_of(request).invalidate_prefix("posts:")
    return attachment
