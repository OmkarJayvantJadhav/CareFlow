"""Shared pieces of the evaluations: the evaluation world, a quota-aware LLM and a resumable store.

* The evaluation database is seeded once for ``EVAL_TODAY`` (seed 42). Every
  conversation runs inside one transaction that is rolled back afterwards, so
  each run starts from exactly the same state without a 16-second reseed.
* ``QuotaLLM`` talks to one model only (no fallback, so every result belongs to
  the model it names), waits out per-minute limits, stops cleanly with
  ``QuotaExhausted`` when the daily quota is gone, and caches responses on disk so
  an interrupted run resumes without spending quota again.
* ``ResultStore`` appends one JSON line per finished case; a rerun skips them.
"""

import hashlib
import json
import logging
import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime
from datetime import time as clock
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.agent.llm import LLMError, LLMResponse, LLMUnavailable, RateLimited, ToolCall, make_provider
from app.config import get_settings
from app.db.models import OPERATIONAL_TABLES, Slot
from app.db.session import session_factory
from app.rag.ingest import ingest
from app.timeutil import at
from simulator.seed import is_seeded, reset_demo

log = logging.getLogger("careflow.eval")
EVAL_TODAY = date(2026, 10, 19)  # a Monday
EVAL_NOW = at(EVAL_TODAY, clock(8, 0))
SEED = 42
CACHE_DIR = Path("eval/.cache")
RESULTS_DIR = Path("eval/results")
RUNS_DIR = Path(os.environ.get("EVAL_RUNS_DIR", "eval/runs"))  # in-progress logs may live elsewhere
MAX_WAIT_SECONDS = 90


class QuotaExhausted(Exception):
    """The model's daily free quota is used up; finished cases are kept and the run can resume later."""


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    from app.db.session import normalize_url

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", normalize_url(get_settings().database_url))
    command.upgrade(cfg, "head")


def prepare_world(force: bool = False) -> None:
    """Migrate and seed the evaluation database for EVAL_TODAY and ingest the knowledge base, if not done yet."""
    migrate()
    with session_factory()() as db:
        seeded = is_seeded(db) and db.scalar(
            select(func.count()).select_from(Slot).where(func.date(Slot.start_at) == EVAL_TODAY)
        )
        if force or not seeded:
            print(f"seeding the evaluation database for {EVAL_TODAY} …", file=sys.stderr)
            reset_demo(db, EVAL_TODAY, SEED)
        ingest(db, if_needed=True)
        db.commit()


def reset_sequences(db: Session) -> None:
    """Point every id sequence just past the seeded rows. Sequences are not rolled back with a transaction,
    so without this each run would see different ids in tool results - and miss the response cache."""
    rows = db.execute(
        text(
            "SELECT table_name, pg_get_serial_sequence(table_name, column_name) FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = 'id' "
            "AND (column_default LIKE 'nextval%' OR is_identity = 'YES')"
        )
    ).all()
    for table, sequence in rows:
        if table in OPERATIONAL_TABLES and sequence:
            db.execute(
                text(f"SELECT setval(:s, COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"), {"s": sequence}
            )


@contextmanager
def isolated() -> Iterator[Session]:
    """A session whose changes are all rolled back at the end; ids start from the same values every time."""
    db = session_factory()()
    try:
        reset_sequences(db)
        yield db
    finally:
        db.rollback()
        db.close()


def _response_to_dict(r: LLMResponse) -> dict:
    return {**asdict(r), "tool_calls": [asdict(c) for c in r.tool_calls]}


def _response_from_dict(d: dict) -> LLMResponse:
    return LLMResponse(**{**d, "tool_calls": [ToolCall(**c) for c in d["tool_calls"]]})


class QuotaLLM:
    """One model, with per-minute waiting, a daily-quota stop and a response cache."""

    def __init__(self, spec: str, salt: str = "", cache: bool = True):
        provider = make_provider(spec, get_settings())
        if provider is None:
            raise SystemExit(f"{spec}: no API key configured (set GROQ_API_KEY / GEMINI_API_KEY)")
        self.provider = provider
        self.name = spec
        self.salt = salt
        self.cache = cache
        self.calls = 0
        self.cached = 0
        self.waited = 0.0
        self.seconds_inside = 0.0  # wall time spent in chat(), including quota waits and cache reads

    def with_salt(self, salt: str) -> "QuotaLLM":
        clone = QuotaLLM.__new__(QuotaLLM)
        clone.__dict__.update(self.__dict__)
        clone.salt = salt
        return clone

    def _key(self, messages: list[dict], tools: list[dict], max_tokens: int) -> Path:
        blob = json.dumps([self.name, self.salt, messages, tools, max_tokens], sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(blob.encode()).hexdigest()
        return CACHE_DIR / digest[:2] / f"{digest}.json"

    def chat(self, messages: list[dict], tools: list[dict], max_tokens: int) -> LLMResponse:
        started = time.perf_counter()
        try:
            return self._chat(messages, tools, max_tokens)
        finally:
            self.seconds_inside += time.perf_counter() - started

    def _chat(self, messages: list[dict], tools: list[dict], max_tokens: int) -> LLMResponse:
        path = self._key(messages, tools, max_tokens)
        if self.cache and path.exists():
            self.cached += 1
            return _response_from_dict(json.loads(path.read_text()))
        for attempt in range(8):
            try:
                response = self.provider.chat(messages, tools, max_tokens)
                break
            except RateLimited as err:
                if err.daily:
                    raise QuotaExhausted(f"{self.name}: daily quota used up ({err})") from None
                wait = min(max(err.retry_after or 5.0, 1.0) + 0.5, MAX_WAIT_SECONDS)
                if err.retry_after and err.retry_after > MAX_WAIT_SECONDS:
                    raise QuotaExhausted(f"{self.name}: rate limited for {err.retry_after:.0f}s") from None
                self.waited += wait
                time.sleep(wait)
            except LLMError as err:
                if attempt >= 2:
                    # Reported like a provider outage: the turn fails, the run goes on.
                    raise LLMUnavailable(str(err)) from None
                time.sleep(3 * (attempt + 1))
        else:
            raise QuotaExhausted(f"{self.name}: still rate limited after repeated waits")
        self.calls += 1
        if self.cache:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(_response_to_dict(response), ensure_ascii=False))
        return response


class ResultStore:
    """Append-only JSONL of finished cases, keyed by ``key``."""

    def __init__(self, path: Path):
        self.path = path
        self.records: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text().splitlines():
                if line.strip():
                    record = json.loads(line)
                    self.records[record["key"]] = record

    def done(self, key: str) -> bool:
        return key in self.records

    def add(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self.records[record["key"]] = record


def load_jsonl(path: str | Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_result(name: str, data: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / name
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n")
    return path


def run_header(**extra) -> dict:
    settings = get_settings()
    return {
        "run_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "eval_clock": EVAL_NOW.isoformat(),
        "embedding_backend": settings.embedding_backend,
        "reranker_backend": settings.reranker_backend,
        "git_commit": os.popen("git rev-parse --short HEAD 2>/dev/null").read().strip() or None,
        # Uncommitted changes to code (not to results or run logs) mean the commit above is not the code that ran.
        "uncommitted_code_changes": bool(
            os.popen("git status --porcelain -- app eval/*.py simulator 2>/dev/null").read().strip()
        ),
        **extra,
    }
