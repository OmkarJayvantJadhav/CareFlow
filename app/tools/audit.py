"""Audit logging for every write tool (FR-33, TC-16)."""

import functools
import inspect
from collections.abc import Callable
from datetime import date, datetime, time
from typing import Any, TypeVar

from sqlalchemy.orm import Session

from app.db.models import AuditLog
from app.safety.privacy import mask_payload
from app.timeutil import resolve_now
from app.tools.errors import ToolError
from app.tools.permissions import Actor

F = TypeVar("F", bound=Callable[..., Any])


def _jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    return value


def record_audit(db: Session, actor: Actor, tool: str, arguments: dict, result: dict, at: datetime) -> None:
    db.add(
        AuditLog(
            user_id=actor.user_id,
            role=actor.role,
            tool=tool,
            arguments=mask_payload(_jsonable(arguments)),
            result=mask_payload(_jsonable(result)),
            at=at,
        )
    )
    db.flush()


def write_tool(name: str) -> Callable[[F], F]:
    """Wrap a write operation so that it is atomic and always audited.

    The operation runs inside a savepoint. On success the audit row records the
    result; on a ToolError the savepoint is rolled back (nothing partially
    executes), a failure row is recorded and the error is re-raised. Callers
    commit the outer transaction in both cases.
    """

    def decorator(fn: F) -> F:
        signature = inspect.signature(fn)

        @functools.wraps(fn)
        def wrapper(db: Session, actor: Actor, *args: Any, **kwargs: Any) -> Any:
            bound = signature.bind(db, actor, *args, **kwargs)
            arguments = {k: v for k, v in bound.arguments.items() if k not in ("db", "actor", "now")}
            at = resolve_now(bound.arguments.get("now"))
            savepoint = db.begin_nested()
            try:
                result = fn(db, actor, *args, **kwargs)
                savepoint.commit()
            except ToolError as err:
                savepoint.rollback()
                record_audit(db, actor, name, arguments, {"ok": False, "error": err.code}, at)
                raise
            except Exception:
                savepoint.rollback()
                raise
            record_audit(db, actor, name, arguments, {"ok": True, "data": result}, at)
            return result

        return wrapper  # type: ignore[return-value]

    return decorator
