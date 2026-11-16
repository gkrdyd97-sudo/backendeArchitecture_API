from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import get_settings
from tests.conftest import signup_and_login


async def test_health(client):
    res = await client.get("/health")
    assert res.status_code == 200
    assert "X-Request-ID" in res.headers and "X-Process-Time-Ms" in res.headers


# ---------------- 인증 ----------------
async def test_signup_login_me(client):
    res = await client.post("/api/v1/auth/signup", json={"email": "kim@example.com", "username": "kim", "password": "password123"})
    assert res.status_code == 201
    assert "hashed_password" not in res.json() and "password" not in res.json()

    res = await client.post("/api/v1/auth/login", data={"username": "kim@example.com", "password": "password123"})
    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 30 * 60

    res = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert res.json()["email"] == "kim@example.com"


async def test_signup_duplicate_and_validation(client):
    await client.post("/api/v1/auth/signup", json={"email": "dup@example.com", "username": "dup", "password": "password123"})
    res = await client.post("/api/v1/auth/signup", json={"email": "dup@example.com", "username": "dup2", "password": "password123"})
    assert res.status_code == 409 and res.json()["error"]["code"] == "DUPLICATE_EMAIL"

    res = await client.post("/api/v1/auth/signup", json={"email": "not-email", "username": "a", "password": "short"})
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert {d["field"] for d in error["details"]} == {"email", "username", "password"}
    assert res.json()["request_id"]


async def test_login_wrong_password(client):
    await signup_and_login(client, "pw")
    res = await client.post("/api/v1/auth/login", data={"username": "pw@example.com", "password": "wrong1234"})
    assert res.status_code == 401 and res.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_token_errors(client):
    res = await client.get("/api/v1/users/me")
    assert res.status_code == 401 and res.json()["error"]["code"] == "UNAUTHORIZED"

    res = await client.get("/api/v1/users/me", headers={"Authorization": "Bearer garbage"})
    assert res.json()["error"]["code"] == "INVALID_TOKEN"

    s = get_settings()
    expired = jwt.encode(
        {"sub": "1", "type": "access", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        s.jwt_secret_key, algorithm=s.jwt_algorithm,
    )
    res = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {expired}"})
    assert res.status_code == 401 and res.json()["error"]["code"] == "TOKEN_EXPIRED"


# ---------------- 게시글 CRUD + 인가 ----------------
async def test_post_crud_and_author_check(client):
    owner = await signup_and_login(client, "owner")
    other = await signup_and_login(client, "other")

    res = await client.post("/api/v1/posts", json={"title": "제목", "content": "내용"})
    assert res.status_code == 401

    res = await client.post("/api/v1/posts", json={"title": "제목", "content": "내용"}, headers=owner)
    assert res.status_code == 201
    post_id = res.json()["id"]

    res = await client.get(f"/api/v1/posts/{post_id}")
    assert res.status_code == 200 and res.json()["view_count"] == 1

    res = await client.patch(f"/api/v1/posts/{post_id}", json={"title": "남이 수정"}, headers=other)
    assert res.status_code == 403 and res.json()["error"]["code"] == "NOT_AUTHOR"

    res = await client.patch(f"/api/v1/posts/{post_id}", json={"title": "수정된 제목"}, headers=owner)
    assert res.status_code == 200 and res.json()["title"] == "수정된 제목" and res.json()["content"] == "내용"

    res = await client.patch(f"/api/v1/posts/{post_id}", json={}, headers=owner)
    assert res.status_code == 422

    res = await client.delete(f"/api/v1/posts/{post_id}", headers=other)
    assert res.status_code == 403
    res = await client.delete(f"/api/v1/posts/{post_id}", headers=owner)
    assert res.status_code == 204
    res = await client.get(f"/api/v1/posts/{post_id}")
    assert res.status_code == 404 and res.json()["error"]["code"] == "POST_NOT_FOUND"


async def test_blank_title_rejected(client):
    h = await signup_and_login(client, "blank")
    res = await client.post("/api/v1/posts", json={"title": "   ", "content": "내용"}, headers=h)
    assert res.status_code == 422 and res.json()["error"]["details"][0]["field"] == "title"


async def test_list_pagination_search_cache(client):
    h = await signup_and_login(client, "lister")
    for i in range(12):
        await client.post("/api/v1/posts", json={"title": f"검색대상 {i}", "content": "본문"}, headers=h)

    res = await client.get("/api/v1/posts", params={"q": "검색대상", "page": 2, "size": 5})
    body = res.json()
    assert body["total"] == 12 and body["pages"] == 3 and len(body["items"]) == 5
    assert res.headers["X-Cache"] == "MISS"
    res = await client.get("/api/v1/posts", params={"q": "검색대상", "page": 2, "size": 5})
    assert res.headers["X-Cache"] == "HIT"

    # 새 글을 쓰면 캐시가 지워져 바로 반영
    await client.post("/api/v1/posts", json={"title": "검색대상 new", "content": "본문"}, headers=h)
    res = await client.get("/api/v1/posts", params={"q": "검색대상", "page": 2, "size": 5})
    assert res.headers["X-Cache"] == "MISS" and res.json()["total"] == 13

    res = await client.get("/api/v1/posts", params={"size": 999})
    assert res.status_code == 422


async def test_comments(client):
    writer = await signup_and_login(client, "writer")
    reader = await signup_and_login(client, "reader")
    post_id = (await client.post("/api/v1/posts", json={"title": "댓글", "content": "글"}, headers=writer)).json()["id"]

    res = await client.post(f"/api/v1/posts/{post_id}/comments", json={"content": "좋아요"}, headers=reader)
    assert res.status_code == 201 and res.json()["author"]["username"] == "reader"
    comment_id = res.json()["id"]

    lst = (await client.get("/api/v1/posts", params={"size": 50})).json()
    assert any(p["id"] == post_id and p["comment_count"] == 1 for p in lst["items"])

    res = await client.delete(f"/api/v1/comments/{comment_id}", headers=writer)
    assert res.status_code == 403
    res = await client.delete(f"/api/v1/comments/{comment_id}", headers=reader)
    assert res.status_code == 204

    res = await client.post("/api/v1/posts/999999/comments", json={"content": "x"}, headers=reader)
    assert res.status_code == 404


async def test_upload(client):
    h = await signup_and_login(client, "uploader")
    other = await signup_and_login(client, "notowner")
    post_id = (await client.post("/api/v1/posts", json={"title": "첨부", "content": "글"}, headers=h)).json()["id"]

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    res = await client.post(f"/api/v1/posts/{post_id}/attachments", files={"file": ("a.png", png, "image/png")}, headers=h)
    assert res.status_code == 201
    url = res.json()["url"]
    assert (await client.get(url)).content == png

    res = await client.post(f"/api/v1/posts/{post_id}/attachments", files={"file": ("a.exe", b"MZ", "application/x-msdownload")}, headers=h)
    assert res.status_code == 415

    res = await client.post(f"/api/v1/posts/{post_id}/attachments", files={"file": ("a.png", png, "image/png")}, headers=other)
    assert res.status_code == 403

    big = b"0" * (get_settings().max_upload_bytes + 1)
    res = await client.post(f"/api/v1/posts/{post_id}/attachments", files={"file": ("big.png", big, "image/png")}, headers=h)
    assert res.status_code == 413

    detail = (await client.get(f"/api/v1/posts/{post_id}")).json()
    assert len(detail["attachments"]) == 1


async def test_unknown_route(client):
    res = await client.get("/api/v1/nope")
    assert res.status_code == 404 and res.json()["error"]["code"] == "NOT_FOUND"
