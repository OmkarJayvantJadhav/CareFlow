from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings


def normalize_url(url: str) -> str:
    """Accept plain postgres URLs (e.g. Neon's) and use the psycopg 3 driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


# Connection poolers in transaction mode (Neon's pooled connection string is one) do not carry everything a
# direct connection does (D-128, D-129):
# - psycopg prepares a statement on the server after five runs; the next run may reach another server
#   connection ("prepared statement already exists"). Statements are never prepared.
# - psycopg runs executemany() (SQLAlchemy uses it for an UPDATE of many rows) in pipeline mode; on Neon the
#   following COMMIT then failed with "received 2 results from command 'COMMIT'". Each row is sent on its own.
CONNECT_ARGS = {"prepare_threshold": None}


def _execute_rows_one_by_one(cursor, statement, parameters, context) -> bool:
    total = 0
    for row in parameters:
        cursor.execute(statement, row)
        total += max(cursor.rowcount, 0)
    # The ORM checks that an UPDATE of n rows matched n rows; cursor.rowcount would only count the last one.
    # SQLAlchemy reads this attribute before the cursor's (DefaultExecutionContext._setup_result_proxy).
    context._rowcount = total
    return True


def without_pipelines(engine: Engine) -> Engine:
    event.listen(engine, "do_executemany", _execute_rows_one_by_one)
    return engine


def make_engine(url: str | None = None) -> Engine:
    return without_pipelines(
        create_engine(
            normalize_url(url or get_settings().database_url),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=5,
            connect_args=CONNECT_ARGS,
        )
    )


_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine, _factory
    if _engine is None:
        _engine = make_engine()
        _factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _factory is not None
    return _factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """A session that commits on success and rolls back on any exception."""
    db = session_factory()()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
