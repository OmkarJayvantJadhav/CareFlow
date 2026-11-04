# PostgreSQL

## 30-second answer
PostgreSQL is an open-source, ACID-compliant relational database known for correctness and extensibility — rich types (JSONB, arrays, `tsvector`), partial and expression indexes, CTEs, window functions, row-level locking, roles and extensions like **pgvector**. CareFlow runs on **PostgreSQL 16 with pgvector** (Docker `pgvector/pgvector:pg16` locally and in CI, **Neon** serverless Postgres in production). I used Postgres features for correctness and safety: **partial unique indexes + `SELECT … FOR UPDATE`** to make double booking impossible, **savepoints** for the agent's preview, **reporting views and a SELECT-only role** for the analytics agent, **READ ONLY transactions with `statement_timeout`**, a **vector column with an HNSW index**, and a **`tsvector` column with a GIN index**.

---

## Basics you must know

### ACID
- **Atomicity** — all or nothing (transaction).
- **Consistency** — constraints always hold.
- **Isolation** — concurrent transactions don't see each other's partial work.
- **Durability** — committed data survives crashes (write-ahead log, WAL).

### MVCC (Multi-Version Concurrency Control)
Each row update creates a new version; readers see a snapshot and **don't block writers** (and vice versa). Old versions are cleaned by **VACUUM**.

### Isolation levels
`READ COMMITTED` (default), `REPEATABLE READ`, `SERIALIZABLE`. Even at READ COMMITTED, two transactions can both "see" a free slot — hence explicit row locks or unique constraints.

### Locks
- `SELECT … FOR UPDATE` — lock selected rows until commit; others wait.
- `FOR UPDATE SKIP LOCKED` — skip rows locked by others (job queues).
- Deadlocks: avoid by locking in a consistent order.

### Indexes
| Type | Use |
|---|---|
| B-tree (default) | Equality, ranges, sorting |
| **Partial** (`WHERE …`) | Index/uniqueness on a subset of rows |
| Unique | Enforce uniqueness |
| **GIN** | `tsvector` full-text, JSONB, arrays |
| GiST | Geometry, ranges |
| **HNSW / IVFFlat** (pgvector) | Approximate nearest-neighbour vector search |

`EXPLAIN ANALYZE` shows the query plan and real timings.

### Other features
Schemas (namespaces), views and materialized views, CTEs (`WITH`), window functions, JSONB, `generated` (computed) columns, roles and `GRANT`, extensions (`CREATE EXTENSION`), `LISTEN/NOTIFY`, savepoints, `SET LOCAL` (only for the current transaction).

### Connection pooling
Postgres uses a process per connection, so apps use pools (SQLAlchemy pool) and/or a pooler (PgBouncer). In **transaction pooling** mode, session state like server-side prepared statements is not safe.

---

## How I used it in CareFlow

### Hosting
- **Local / CI:** `pgvector/pgvector:pg16` in `docker-compose.yml` and as a GitHub Actions service container, with `pg_isready` health checks.
- **Production:** **Neon** free tier (serverless Postgres with pgvector, region Singapore). Neon suspends compute when idle → `pool_pre_ping=True`; its pooled connection string runs in transaction mode → **prepared statements disabled** (`prepare_threshold: None`, decision D-128).

### Schema — 28 tables (`app/db/models.py`, 12 Alembic migrations)
Departments, doctors, slots, patients, users, appointments, waiting list, queue sessions/entries/events, wait predictions, knowledge-base documents/chunks, notifications, consents, audit log, conversations, settings, …

### Correctness with constraints and locks
```sql
-- one ACTIVE booking per slot; cancelled ones don't count
CREATE UNIQUE INDEX uq_appointment_active_slot ON appointment (slot_id)
  WHERE status IN ('booked', 'rescheduled');
-- one active appointment per patient, doctor and day
CREATE UNIQUE INDEX uq_appointment_active_patient_doctor_day ON appointment (patient_id, doctor_id, appt_date)
  WHERE status IN ('booked', 'rescheduled');
```
- Booking locks the slot rows with `SELECT … FOR UPDATE` **in id order** (no deadlocks).
- `CHECK` constraints on status values; `UNIQUE (doctor_id, start_at)` on slots; `UNIQUE (session_id, token)` on queue entries.
- Job tables (outbox, waiting-list offers) are claimed with `FOR UPDATE SKIP LOCKED`.
- Tested with a 10-thread race: exactly one booking wins.

### Savepoints
The agent previews a write inside `SAVEPOINT … ROLLBACK TO SAVEPOINT` (SQLAlchemy `begin_nested()`), so the confirmation card reflects real constraint checks without changing data.

### Safe analytics (`alembic/versions/0003…`, `app/analytics/sql_guard.py`)
- Schema **`reporting`** with views that exclude names and phone numbers.
- Role **`careflow_analytics`** (NOLOGIN) with `USAGE` on the schema and `SELECT` on the views only.
- Each analytics query runs:
  ```sql
  BEGIN;
  SET TRANSACTION READ ONLY;
  SET LOCAL statement_timeout = 3000;
  SET LOCAL ROLE careflow_analytics;      -- if the host allowed creating it
  SET LOCAL search_path = reporting;
  SELECT * FROM (<validated query>) AS analytics_result LIMIT 201;
  ROLLBACK;
  ```

### Vector + full-text search on the same table (`kb_chunk`)
- `embedding vector(384)` with an **HNSW** index (`vector_cosine_ops`) — see [pgvector](pgvector.md).
- `tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', section || ' ' || text)) STORED` with a **GIN** index — `simple` config because Postgres has no Hindi/Marathi stemmer.

### Privacy at rest
Phone numbers and e-mails stored **AES-GCM encrypted** plus an HMAC index for exact lookup — the database never holds them in clear text.

### Tests use a real Postgres
`tests/conftest.py` drops and recreates the `public` schema, runs all migrations once, and **`TRUNCATE … RESTART IDENTITY CASCADE`** operational tables before each test — so concurrency, partial indexes and pgvector behave exactly as in production.

---

## Interview questions

**Q: Why PostgreSQL over MySQL or MongoDB?**
Strong constraints (partial unique indexes, CHECK), mature transactions and locking, roles/views for least privilege, and pgvector so relational data and vector search live in one database — no separate vector DB.

**Q: How do you stop two users booking the same slot?**
Lock the slot row with `SELECT … FOR UPDATE` so concurrent bookers queue up, and back it with a partial unique index on active appointments so even a bug can't create a duplicate.

**Q: What is a partial index?**
An index over rows matching a `WHERE` clause. As a unique index, it enforces uniqueness only for those rows — e.g. only active appointments.

**Q: What is MVCC?**
Rows have versions; each transaction reads a consistent snapshot, so reads don't block writes. VACUUM reclaims old versions.

**Q: How did you make text-to-SQL safe?**
Validate the SQL (one SELECT over allowed views), then run it read-only, with a timeout, a row limit, a restricted search_path and a SELECT-only role — defence in depth.

**Q: What issue did you hit with Neon?**
Its pooled endpoint uses transaction pooling; psycopg's automatic prepared statements broke ("prepared statement already exists"), so I disabled them. Also idle suspend → pre-ping connections.
