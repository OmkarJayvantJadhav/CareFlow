"""Request dependencies: database session, authenticated actor, LLM, rate limiting."""

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.agent.llm import FallbackLLM, build_llm
from app.api.auth import verify_token
from app.db.session import session_factory
from app.tools.errors import ToolError
from app.tools.permissions import Actor


def get_db() -> Iterator[Session]:
    db = session_factory()()
    try:
        yield db
    finally:
        db.rollback()
        db.close()


def run_and_commit(db: Session, fn: Callable[[], Any]) -> Any:
    """Commit after success and after a rule failure: a refused write was rolled back
    to its savepoint inside the tool, and its audit row must still be kept."""
    try:
        result = fn()
    except ToolError:
        db.commit()
        raise
    db.commit()
    return result


@dataclass
class Auth:
    actor: Actor
    session_id: str
    expires_at: datetime


def get_auth(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> Auth:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ToolError("UNAUTHORIZED", "Sign in first: send 'Authorization: Bearer <token>'.")
    actor, session_id, expires = verify_token(db, authorization.split(" ", 1)[1].strip())
    return Auth(actor, session_id, expires)


@lru_cache
def _llm() -> FallbackLLM:
    return build_llm()


def get_llm() -> FallbackLLM:
    return _llm()


class SlidingWindowLimiter:
    """In-process limiter (one instance per app; the demo runs a single process)."""

    def __init__(self, window_seconds: float):
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def check(self, key: str, limit: int) -> None:
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= limit:
                retry_after = int(hits[0] + self.window - now) + 1
                raise ToolError("RATE_LIMITED", "Too many messages; please wait a little.", retry_after=retry_after)
            hits.append(now)


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
