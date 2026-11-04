# SQLAlchemy

## 30-second answer
SQLAlchemy is Python's main database toolkit: **Core** builds SQL with Python expressions, and the **ORM** maps classes to tables and rows to objects, with a **Session** that manages transactions (unit of work). CareFlow uses **SQLAlchemy 2.0** with typed models (`Mapped[...]`, `mapped_column`) for its **28 tables** on PostgreSQL via the psycopg 3 driver. The important parts are database-level correctness: **partial unique indexes** and **`SELECT … FOR UPDATE` row locks** that make double booking impossible, **savepoints** (`begin_nested()`) that let the LLM agent preview a write and roll it back, and the **pgvector** `Vector(384)` column with an HNSW index for retrieval.

---

## Basics you must know

### Engine, connection, session
```python
engine = create_engine("postgresql+psycopg://user:pw@host/db", pool_pre_ping=True, pool_size=5)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
with SessionLocal() as db:
    db.add(obj); db.commit()
```
- **Engine:** connection pool + dialect.
- **Session:** a unit of work — tracks objects, flushes changes, commits or rolls back.
- **Identity map:** one Python object per row per session.

### Declarative models (2.0 style)
```python
class Base(DeclarativeBase): ...

class Appointment(Base):
    __tablename__ = "appointment"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patient_id: Mapped[int] = mapped_column(ForeignKey("patient.id"))
    status: Mapped[str] = mapped_column(String(12), default="booked")
    patient: Mapped["Patient"] = relationship()
```

### Querying (2.0 style)
```python
db.scalars(select(Doctor).where(Doctor.department_id == 3).order_by(Doctor.name)).all()
db.get(Patient, 7)                                    # by primary key
db.execute(select(func.count(KbChunk.id))).scalar()
```

### Transactions
- `db.commit()`, `db.rollback()`.
- **Savepoints:** `sp = db.begin_nested()` → `sp.rollback()` undoes only inside the savepoint.
- Isolation levels; `SELECT ... FOR UPDATE` via `.with_for_update()`; `skip_locked=True` for job queues.

### Relationships and loading
`relationship()`, `back_populates`, lazy loading vs eager loading (`selectinload`, `joinedload`) to avoid the **N+1 query problem**.

### Constraints and indexes
`UniqueConstraint`, `CheckConstraint`, `Index(..., unique=True, postgresql_where=...)` (partial index), `postgresql_using="gin"/"hnsw"`, `Computed(...)` columns.

### Raw SQL when needed
`db.execute(text("SET TRANSACTION READ ONLY"))`.

---

## How I used it in CareFlow

### Engine and sessions (`app/db/session.py`)
```python
def make_engine(url=None):
    return create_engine(normalize_url(url or settings.database_url),
                         pool_pre_ping=True, pool_size=5, max_overflow=5,
                         connect_args={"prepare_threshold": None})
```
- `normalize_url` accepts Neon's `postgres://…` and switches to the **psycopg 3** driver.
- `pool_pre_ping` — test connections before use (Neon suspends idle compute).
- **`prepare_threshold: None`** — psycopg prepares statements after 5 runs; through Neon's **transaction-mode pooler** the next run might hit another server connection ("prepared statement already exists"), so statements are never prepared (decision D-128).
- `session_scope()` — a context manager that commits on success and rolls back on any exception.

### Models (`app/db/models.py`) — 28 tables
Departments, doctors, slots, patients, users, caregiver links, appointments, waiting list, queue sessions/entries/events, wait predictions, knowledge-base documents/chunks, notifications, registration fields, consents, leave, priority rules/requests, audit log, conversations, handoff tickets, policy and messaging settings, hospital profile…

### Correctness in the database, not just in code
**Partial unique indexes:**
```python
Index("uq_appointment_active_slot", "slot_id", unique=True,
      postgresql_where=text("status IN ('booked', 'rescheduled')"))          # one ACTIVE booking per slot
Index("uq_appointment_active_patient_doctor_day", "patient_id", "doctor_id", "appt_date", unique=True,
      postgresql_where=text("status IN ('booked', 'rescheduled')"))          # no duplicate booking that day
```
Cancelled appointments don't count, so a slot can be re-booked. `doctor_id` and `appt_date` are denormalised onto the appointment so this rule *can* be an index.

**Row locks** (`app/tools/booking.py`):
```python
def _lock_slots(db, *slot_ids):
    """Lock slot rows in id order (avoids deadlocks) and re-read them from the database."""
    rows = db.scalars(select(Slot).where(Slot.id.in_(slot_ids)).order_by(Slot.id)
                      .with_for_update().execution_options(populate_existing=True))
```
- `with_for_update()` → `SELECT ... FOR UPDATE`: a second transaction waits until the first commits.
- **Ordering by id** prevents deadlocks when rescheduling locks two slots.
- `populate_existing=True` refreshes objects already in the session with the locked, current values.
- Any race that still slips through hits the unique index → `IntegrityError` → `ToolError("SLOT_TAKEN")` (409).
- `with_for_update(skip_locked=True)` is used for work queues (message outbox, waiting-list offers) so parallel workers don't take the same row.

**Proof** (`tests/test_concurrency.py`): 2 threads and then **10 threads** booking the same slot at the same moment (synchronised with `threading.Barrier`) → exactly one `ok`, the rest `SLOT_TAKEN`; two simultaneous bookings for the same patient/day → one `DUPLICATE`.

### Savepoints for the agent's preview (`app/agent/tools.py`)
```python
savepoint = ctx.db.begin_nested()     # SAVEPOINT
try:
    return fn()                        # real booking logic with all checks
finally:
    savepoint.rollback()               # ROLLBACK TO SAVEPOINT
```

### pgvector and full-text columns (`KbChunk`)
```python
embedding: Mapped[list[float] | None] = mapped_column(Vector(384))
Index("ix_kb_chunk_embedding", "embedding", postgresql_using="hnsw",
      postgresql_ops={"embedding": "vector_cosine_ops"})
tsv = mapped_column(TSVECTOR, Computed("to_tsvector('simple', coalesce(section, '') || ' ' || text)", persisted=True))
```
Query: `KbChunk.embedding.cosine_distance(vector)` in `ORDER BY`.

### Check constraints
`CheckConstraint("status IN (...)")` on appointment status and source.

---

## Interview questions

**Q: ORM vs Core vs raw SQL?**
ORM for business objects and relationships; Core/`text()` for analytics, DDL-ish statements and performance-critical queries. I used the ORM for the app and `text()` for read-only analytics settings.

**Q: How did you prevent double booking?**
Two layers: `SELECT … FOR UPDATE` on the slot rows (serialises concurrent bookers) and partial unique indexes on active appointments (the database refuses a second active booking even if code has a bug). A 10-thread race test proves one winner.

**Q: What is a savepoint and why did you need it?**
A nested transaction you can roll back without ending the outer one. The agent runs the real booking inside a savepoint to see exactly what would happen, then rolls back, so nothing is written until the user confirms.

**Q: How do you avoid deadlocks?**
Always lock rows in the same order (by id), keep transactions short.

**Q: What is the N+1 problem?**
Loading a list then lazily loading a relationship for each item = N extra queries. Fix with `selectinload`/`joinedload` or a join.

**Q: Why `expire_on_commit=False`?**
So objects can still be read after commit (e.g. to build the response) without a new query per attribute.
