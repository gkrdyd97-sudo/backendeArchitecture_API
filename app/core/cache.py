"""아주 단순한 메모리 TTL 캐시.

자주 읽고 드물게 바뀌는 게시글 목록·상세 조회 결과를 잠시 저장해 DB 조회를 줄인다.
쓰기(생성·수정·삭제)가 일어나면 관련 키를 지워 오래된 데이터가 보이지 않게 한다.
서버가 여러 대면 Redis 같은 공유 캐시로 바꿔야 한다.
"""
import time
from typing import Any


class TTLCache:
    def __init__(self, ttl_seconds: int):
        self.ttl = ttl_seconds
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        expires_at, value = item
        if expires_at < time.monotonic():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic() + self.ttl, value)

    def invalidate_prefix(self, prefix: str) -> None:
        for key in [k for k in self._store if k.startswith(prefix)]:
            self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()
