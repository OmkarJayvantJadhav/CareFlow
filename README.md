# CareFlow

> **Demo with a fictional hospital. Not for medical use.** All patients, doctors and schedules are synthetic.

CareFlow is a hospital assistant for OPD (outpatient) visits at the fictional
**Indravani General Hospital**: patients book, reschedule and cancel appointments
through conversation, get cited answers from hospital documents, and see a live
queue with predicted waiting times. Every behaviour is meant to be proven by an
automated evaluation suite.

The full specification (problem statement, PRD, SRS, architecture, database, API,
UI, test plan, roadmap, security, deployment, risks, evaluation) is in
[`docs/CareFlow-Project-Documentation.md`](docs/CareFlow-Project-Documentation.md).
Decisions taken where the spec is silent are in [`docs/DECISIONS.md`](docs/DECISIONS.md).

## Current state: Phase 1 — Foundation ✅

| Phase | Scope | Status |
| --- | --- | --- |
| 1. Foundation | Schema + migrations, hospital simulator, seed data, core booking and queue functions, unit tests | **Done** |
| 2. Agent + RAG | Knowledge base, hybrid retrieval + re-ranker, agent loop, safety gate, chat API | Not started |
| 3. Queue + ML | Queue events over WebSocket, wait-time model + baselines, queue tools | Not started |
| 4. Evaluation | 120 agent scenarios, user simulator, RAG/ML/safety sets, results table | Not started |
| 5. Ship | Patient and staff UI, admin dashboard, analytics agent, deployment | Not started |

What works today:

- **Database** — PostgreSQL + pgvector, 17 tables, Alembic migration. Double booking and duplicate
  bookings are impossible at the database level (row lock + partial unique indexes);
  `audit_log`, `queue_event` and `wait_prediction` are append-only (enforced by triggers).
- **Booking rules in code** (`app/tools/`) — doctor search by specialty / language / day (English,
  Hindi, Marathi aliases), free-slot listing, book / reschedule / cancel with explicit
  confirmation, policy windows, duplicate detection, waiting list with offer-first holds,
  caregiver links, appointment history. Roles and ownership are checked inside every function.
- **Queue engine** (`app/queue/`) — check-in, walk-in tokens, configurable merge rule, calling,
  consultations, missed turn / return, priority (staff only, audited), break, delay, emergency,
  doctor unavailability (patients notified, appointments released for rebooking), session close
  with no-shows. Positions are recomputed after every event.
- **Audit and privacy** — every write (successful or refused) is audited with masked arguments;
  phone numbers are masked in storage, audit rows, event payloads, notifications and logs.
- **Hospital simulator** (`simulator/`) — seeds the hospital, 400 synthetic patients, 3 weeks of
  slots and bookings; replays full OPD days through the real service functions; checks every
  replayed day against invariants; demo reset.
- **API** — `GET /api/v1/health` (the rest of the API arrives in Phase 2).

No evaluation has been run yet, so there are no results to report.

## Quick start (Docker)

Requirements: Docker with Compose.

```bash
docker compose up --build
```

This starts PostgreSQL + pgvector and the API, runs the migrations, seeds the database on first
start, and serves on <http://localhost:8000>:

- Health check: <http://localhost:8000/api/v1/health>
- OpenAPI docs: <http://localhost:8000/docs>

Replay a full synthetic hospital day and check its invariants:

```bash
docker compose exec api python -m simulator replay-day --date 2026-10-17
```

## Local development (without the API container)

Requirements: Python 3.11+, and PostgreSQL 16 with the pgvector extension (the Compose `db`
service is the easiest way to get one).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                       # adjust DATABASE_URL if needed

docker compose up -d db                    # or use your own Postgres + pgvector
alembic upgrade head                       # create the schema
python -m simulator seed                   # load the fictional hospital
uvicorn app.api.main:app --reload          # http://localhost:8000
```

### Simulator commands

| Command | What it does |
| --- | --- |
| `python -m simulator seed [--if-empty]` | Load departments, doctors, demo accounts, 400 synthetic patients, 21 days of slots and upcoming bookings |
| `python -m simulator reset` | Demo reset (FR-34): wipe operational tables and reload exactly the same seed data |
| `python -m simulator replay-day --date YYYY-MM-DD` | Simulate every OPD session of a day (arrivals, no-shows, late patients, walk-ins, breaks, emergencies, missed turns, doctor absence) and print a report with invariant checks; exits non-zero if any invariant fails |
| `python -m simulator history --days 90` | Replay the 90 days before today (training data for the Phase 3 wait-time model) |

All randomness is seeded (`SIMULATOR_SEED`, default 42), so runs are reproducible.

### Tests

The tests run against a real PostgreSQL + pgvector database (they drop and recreate its schema),
so point them at a **dedicated** test database:

```bash
docker compose exec db createdb -U careflow careflow_test     # once
export TEST_DATABASE_URL=postgresql+psycopg://careflow:careflow@localhost:5432/careflow_test
pytest                       # unit, integration and concurrency tests
ruff check . && ruff format --check .
```

GitHub Actions runs lint, the full test suite (with a pgvector service container) and a Docker
build on every push.

## Configuration

Environment variables (see `.env.example`); names follow docs §12.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | local Postgres | Postgres connection string (Neon's `postgresql://…` form is accepted) |
| `QUEUE_MERGE_RULE` | `slot_order` | `slot_order` (booked keep slot order, walk-ins fill gaps) or `alternate` |
| `DEMO_MODE` | `true` | Shows the demo banner; enables demo reset |
| `SIMULATOR_SEED` | `42` | Seed for all synthetic data |
| `LLM_PRIMARY`, `LLM_FALLBACK`, `GROQ_API_KEY`, `GEMINI_API_KEY` | | Used from Phase 2 |
| `MAX_MESSAGES_PER_SESSION`, `PROMPT_TOKEN_BUDGET`, `RAG_TOP_K` | 20, 3000, 4 | Used from Phase 2 |

## Business rules (enforced in code)

| Rule | Value |
| --- | --- |
| Rescheduling | Until 12 hours before the appointment (any time if the doctor became unavailable) |
| Cancellation | Until 4 hours before the appointment |
| Booking window | From 15 minutes to 30 days ahead |
| Duplicate booking | One active appointment per patient, doctor and day |
| Waiting list | A freed slot is held for the earliest matching waiting patient for up to 2 hours |
| Late arrival | More than 15 minutes after the slot start → queued by arrival time |
| Confirmation | Every booking change requires `confirmed=true`; otherwise `CONFIRMATION_REQUIRED` and nothing is written |

## Repository layout

```
app/
  api/        FastAPI application
  db/         SQLAlchemy models (17 tables) and sessions
  tools/      booking, waiting list, permissions, audit, policy — the deterministic rules
  queue/      merge rule (pure functions) and queue engine
  safety/     phone masking (emergency gate arrives in Phase 2)
  agent/ rag/ ml/ analytics/   later phases
alembic/      database migrations
simulator/    fictional hospital, seed data, day replay, invariant checks
knowledge/    hospital knowledge-base documents (Phase 2)
eval/         evaluation suites and results (Phase 4)
ui/           React app (Phase 5)
tests/        pytest suite
docs/         specification and DECISIONS.md
```

## Phase 1 traceability

| Requirement | Where | Tests |
| --- | --- | --- |
| FR-07 search doctors | `app/tools/booking.py::search_doctors` | `test_booking.py` |
| FR-08 free slots | `check_availability` | `test_booking.py` |
| FR-09 confirmation before booking | `book_appointment` | TC-01 |
| FR-10 no booking of taken slots | row lock + `uq_appointment_active_slot` | TC-02, TC-03 |
| FR-11 duplicate detection | `uq_appointment_active_patient_doctor_day` | TC-04 |
| FR-12 reschedule within window | `reschedule_appointment` | TC-05, US-03 |
| FR-13 cancel within window | `cancel_appointment` | TC-06 |
| FR-14 waiting list, offer first | `app/tools/waiting_list.py` | TC-07 |
| FR-15 caregiver access | `app/tools/permissions.py` | TC-08, US-10 |
| FR-16 history | `get_patient_appointments` | `test_booking.py` |
| FR-21 walk-ins and tokens | `app/queue/engine.py::register_walk_in` | US-11 |
| FR-22 configurable merge rule | `app/queue/merge.py` | TC-09 |
| FR-23 queue events | `app/queue/engine.py` | TC-10 (positions), `test_queue.py` |
| FR-27 doctor unavailable | `record_doctor_event(type="unavailable")` | TC-12 |
| FR-28 priority, staff only, audited | `set_priority` | TC-13 |
| FR-33 audit log | `app/tools/audit.py` | TC-16 |
| FR-34 demo reset | `simulator/seed.py::reset_demo` | TC-17 |
| NFR-07 roles in tools | every service function | `test_permissions.py` |
| NFR-08 masking | `app/safety/privacy.py` | TC-18 |
| NFR-15 one-command run, CI | `docker-compose.yml`, `.github/workflows/ci.yml` | — |

TC-10 and TC-11 (prediction rows after queue events) are completed in Phase 3 with the wait-time
model; TC-14/15 (analytics), TC-19 (LLM fallback) and TC-20 (live page) belong to later phases.

## Limitations

- Synthetic data only; the simulator's parameters are assumptions (see `docs/DECISIONS.md`, D-21).
- No chat, retrieval, prediction or UI yet — those are Phases 2–5.
- Notifications are mocked (stored in the `notification` table, never sent).
