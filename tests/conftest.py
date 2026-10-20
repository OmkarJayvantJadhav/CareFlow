"""Test fixtures. Tests run against a real PostgreSQL + pgvector database
(TEST_DATABASE_URL), migrated with Alembic once per run and wiped per test."""

import os

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://careflow:careflow@localhost:5432/careflow_test"
)
# Point the application at the test database before anything reads settings. Tests use
# the deterministic local retrieval models and never call a real LLM provider.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["EVAL_DATABASE_URL"] = TEST_DATABASE_URL  # importing the eval package must not leave the test database
os.environ["EMBEDDING_BACKEND"] = "local"
os.environ["RERANKER_BACKEND"] = "local"
os.environ["GROQ_API_KEY"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["WARM_UP_RETRIEVER"] = "false"
os.environ.setdefault("TRACE_DIR", os.path.join(os.path.dirname(__file__), ".traces"))

from dataclasses import dataclass  # noqa: E402
from datetime import date, datetime, timedelta  # noqa: E402

import numpy as np  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.config import HOSPITAL_TZ  # noqa: E402
from app.db.models import OPERATIONAL_TABLES, AppUser, Doctor, Patient, Slot  # noqa: E402
from app.db.session import get_engine, normalize_url  # noqa: E402
from app.timeutil import at  # noqa: E402
from app.tools.permissions import Actor  # noqa: E402
from simulator.seed import ensure_slots, seed_reference  # noqa: E402

# A fixed clock: Monday 19 October 2026, 08:00 in the hospital's time zone.
NOW = datetime(2026, 10, 19, 8, 0, tzinfo=HOSPITAL_TZ)
TODAY = NOW.date()
SATURDAY = date(2026, 10, 24)


@pytest.fixture(scope="session")
def engine():
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", normalize_url(TEST_DATABASE_URL))
    eng = get_engine()
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    command.upgrade(cfg, "head")
    yield eng


def wipe(engine) -> None:
    """Operational data is wiped before every test; the knowledge base is ingested once (see ``kb``)."""
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(OPERATIONAL_TABLES)} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def kb(engine):
    """The real knowledge base, ingested into the test database once per run."""
    from app.rag.ingest import ingest

    factory = sessionmaker(bind=engine)
    with factory() as db:
        result = ingest(db)
        db.commit()
    return result


@pytest.fixture
def factory(engine):
    wipe(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@dataclass
class World:
    db: Session

    def user(self, username: str) -> Actor:
        return Actor.from_user(self.db.scalars(select(AppUser).where(AppUser.username == username)).one())

    def doctor(self, name: str) -> Doctor:
        return self.db.scalars(select(Doctor).where(Doctor.name == name)).one()

    def patient(self, name: str) -> Patient:
        return self.db.scalars(select(Patient).where(Patient.synthetic_name == name)).first()

    def slots(self, doctor: Doctor, day: date) -> list[Slot]:
        ensure_slots(self.db, day, day)
        return list(
            self.db.scalars(
                select(Slot)
                .where(Slot.doctor_id == doctor.id, Slot.start_at >= at(day, datetime.min.time()))
                .where(Slot.start_at < at(day + timedelta(days=1), datetime.min.time()))
                .order_by(Slot.start_at)
            )
        )

    def other_patients(self, n: int) -> list[int]:
        demo = {self.user("asha").patient_id, self.patient("Vinayak Deshmukh").id}
        ids = [p for p in self.db.scalars(select(Patient.id).order_by(Patient.id)) if p not in demo]
        return ids[:n]

    @property
    def asha(self) -> Actor:
        return self.user("asha")

    @property
    def staff(self) -> Actor:
        return self.user("priya")


@pytest.fixture
def world(factory):
    db = factory()
    seed_reference(db, np.random.default_rng(7))
    db.commit()
    yield World(db)
    db.rollback()
    db.close()


@pytest.fixture
def frozen_clock(monkeypatch):
    """Freeze the application clock (everything that reads now_ist) at NOW."""
    import app.api.admin_routes
    import app.api.auth
    import app.api.care_routes
    import app.api.queue_routes
    import app.api.registration_routes
    import app.api.routes
    import app.timeutil

    modules = (app.timeutil, app.api.auth, app.api.queue_routes, app.api.routes, app.api.admin_routes,
               app.api.care_routes, app.api.registration_routes)  # fmt: skip
    for module in modules:
        monkeypatch.setattr(module, "now_ist", lambda: NOW)
    return NOW
