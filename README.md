<div align="center">

# 🏥 CareFlow

**An OPD system for a hospital — appointments, information, check-in, the live queue and messages to
patients — in English, हिन्दी and मराठी.**

Book, reschedule and cancel appointments by chat or in a few taps, get answers cited from the hospital's
own documents, check in from your phone or a kiosk, join a queue online and watch your token move in real
time, with reminders in the app, by SMS or by e-mail. Doctors and the front desk run, balance and
coordinate every queue, and the hospital's admins keep its people, timetables, rules and documents.

[![Live demo](https://img.shields.io/badge/live%20demo-careflow--zy87.onrender.com-0f766e?style=for-the-badge)](https://careflow-zy87.onrender.com)

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.148-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)
![Tests](https://img.shields.io/badge/tests-461%20Python%20·%2044%20browser-15803d)
![Accessibility](https://img.shields.io/badge/WCAG-A%2FAA%20checked-1e40af)

> ⚠️ **The live demo uses a fictional hospital (Indravani General Hospital) and synthetic data. Not for medical use.**
> A hospital runs its own copy with `DEMO_MODE=false`: its own accounts, departments, doctors, rules and documents,
> no demo roles or reset ([production setup](#running-it-for-a-real-hospital)). Phone numbers and e-mail addresses
> are encrypted at rest and shown masked.

</div>

<p align="center">
  <img src="docs/screenshots/chat.png" alt="The assistant proposing a booking on a confirmation card" width="49%">
  <img src="docs/screenshots/book.png" alt="Booking page with ranked, explained time recommendations" width="49%">
</p>

---

## Contents

- [Why CareFlow](#why-careflow)
- [Screenshots](#screenshots)
- [Features](#features)
- [How it works](#how-it-works)
- [Measured results](#measured-results)
- [Quick start](#quick-start)
- [Development and tests](#development-and-tests)
- [Configuration](#configuration)
- [Business rules](#business-rules)
- [Project structure](#project-structure)
- [Limitations](#limitations)
- [Documentation](#documentation)

---

## Why CareFlow

Outpatient departments lose hours to phone queues, double bookings and crowded waiting rooms. CareFlow puts
the whole visit in one place — booking, information, check-in, the queue and messages — and is built
around four principles:

| | Principle | In practice |
| :---: | --- | --- |
| 🛡️ | **Rules live in code, not in the model** | The language model can only *propose* a booking. CareFlow checks it, shows a confirmation card and acts only on an explicit "yes". Policy windows, duplicates and permissions are enforced inside every tool. |
| 🚑 | **Safety first** | Every message is checked for emergencies *before* the model sees it. An emergency gets fixed guidance (call 112 / 108) and nothing is written. Medicine names and doses never reach the user. |
| 🏥 | **The hospital's own** | Nothing about the hospital is hardcoded: its admins manage the accounts, departments, doctors, timetables, booking and queue rules, information documents and which messages are sent. Patient contact details are encrypted, and patients can download or erase their data. |
| 📏 | **Measured, not assumed** | An evaluation suite with held-out test sets measures safety, retrieval and the agent. Every number below comes from a real run and states its sample size. |

---

## Screenshots

<table>
  <tr>
    <td width="50%"><img src="docs/screenshots/start.png" alt="Start page with sign-in, sign-up and demo roles"><br><sub><b>Start</b> — sign in, create an account or try a demo role</sub></td>
    <td width="50%"><img src="docs/screenshots/receipt.png" alt="Printable receipt with a signed QR code"><br><sub><b>Receipt</b> — signed reference code and QR code for check-in</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/front-desk.png" alt="Front desk with code check-in, live queue and bookings"><br><sub><b>Front desk</b> — code check-in, live queue, categories, check-in times</sub></td>
    <td><img src="docs/screenshots/dashboard.png" alt="Admin dashboard with headline numbers and a department chart"><br><sub><b>Admin dashboard</b> — today's numbers, utilization and evaluation results</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/doctor-queue.png" alt="A doctor's own queue with the patient in the room and requests from the front desk"><br><sub><b>Doctor</b> — own queue, forward a patient, authorize priority requests</sub></td>
    <td><img src="docs/screenshots/coordination.png" alt="Department coordination board with expected finish times and balancing suggestions"><br><sub><b>Coordination</b> — every doctor's queue side by side, with balancing moves</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/accounts.png" alt="Accounts page with a new account's temporary password shown once"><br><sub><b>Accounts</b> — admins add staff and doctors; the temporary password is shown once</sub></td>
    <td><img src="docs/screenshots/start-hospital.png" alt="Start page of a hospital's own deployment, without demo roles"><br><sub><b>A hospital's own deployment</b> — sign-in and sign-up, no demo</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/patients.png" alt="A patient's record at the front desk with the full number shown on request"><br><sub><b>Patient records</b> — correct details, see visits, show the number when calling</sub></td>
    <td><p align="center"><img src="docs/screenshots/phone-password-gate.png" alt="Choosing one's own password on a phone" width="46%"></p><sub><b>First sign-in</b> — a temporary password must be replaced</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/documents.png" alt="Editing an information document with rule placeholders"><br><sub><b>Documents</b> — edit what the library shows and the assistant cites</sub></td>
    <td><img src="docs/screenshots/rules.png" alt="The hospital's booking and queue rules"><br><sub><b>Rules</b> — the hospital's own cut-offs and windows</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/hospital-setup.png" alt="Hospital setup: a changed timetable keeps its bookings and lists those outside it"><br><sub><b>Hospital setup</b> — a changed timetable keeps every booking and lists those to call</sub></td>
    <td><p align="center"><img src="docs/screenshots/phone-add-doctor.png" alt="Adding a doctor on a phone in large text" width="46%"></p><sub><b>Phone</b> — every admin screen also works at 360 px in large text</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/messaging.png" alt="The SMS and e-mail page: provider status, the sending switch and the kinds of message"><br><sub><b>SMS and e-mail</b> — off until an admin turns it on; choose which messages go out</sub></td>
    <td><p align="center"><img src="docs/screenshots/phone-contact-choice.png" alt="A patient choosing SMS, e-mail or only in the app on a phone" width="46%"></p><sub><b>The patient's choice</b> — SMS, e-mail or only in the app</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/kiosk.png" alt="Self check-in kiosk"><br><sub><b>Kiosk</b> — self check-in at reception, first name only</sub></td>
    <td>
      <p align="center">
        <img src="docs/screenshots/phone-chat.png" alt="Chat on a phone" width="46%">
        <img src="docs/screenshots/phone-appointments.png" alt="My appointments on a phone" width="46%">
      </p>
      <sub><b>Phone</b> — bottom tab bar, large-text mode, 44 px tap targets</sub>
    </td>
  </tr>
</table>

A recorded walk-through with the real language model is in [`docs/demo/careflow-demo.webm`](docs/demo/careflow-demo.webm)
(recorded before the interface redesign).

---

## Features

### 🧑‍⚕️ For patients and caregivers

| Feature | What you get |
| --- | --- |
| **Assistant chat** | Book, reschedule, cancel or join a waiting list, check in, join a doctor's queue online or leave it — in plain language; a confirmation card (with a countdown) before anything changes; "Talk to a person" at any time. |
| **Book without chatting** | Choose a department, doctor, language, dates and time of day; times are ranked and each says why — *Soonest*, *Speaks your language*, *Doctor you have seen*, *Quieter day*. |
| **Cited answers** | Policies, insurance, test preparation and facilities answered from the hospital's documents, with source chips that open the full document; "I couldn't find that" when the documents don't say. |
| **Hospital information** | Every document the assistant answers from — 121 topics in English, हिन्दी and मराठी — readable and searchable by anyone, without signing in. |
| **My appointments** | Upcoming and past visits, receipt, reschedule, cancel and rebook — every change confirmed in a dialog; actions close automatically inside the policy windows. |
| **Receipts** | A printable receipt with a signed reference code and QR code. |
| **Online check-in** | From an hour before the slot until 15 minutes after it starts; the token appears at once. |
| **Join a queue online** | No appointment? Join a doctor's queue today from your phone (from an hour before OPD opens), come in when your turn is near, or leave the queue if plans change. |
| **Live queue** | Your token, people ahead and "about 35 min (25–50)", updated over a WebSocket in under 2 seconds; a message if the doctor is delayed by an emergency, and your new token if you are moved to another doctor. |
| **Reminders and messages** | The day before and two hours before, in your language, in a notification list with an unread badge — and by SMS or e-mail when the hospital sends them; you choose SMS, e-mail or only in the app. |
| **Profile and privacy** | Edit your details, change your password, switch reminders and reuse of your details on or off, approve or remove caregivers, download all your data, or delete your account. |
| **Accounts** | Create an account with a password — for yourself, or as a caregiver for a family member — or try the demo roles without one. |

### 🧾 For the front desk

| Feature | What you get |
| --- | --- |
| **Today at a glance** | Every doctor on duty, their bookings, check-in and check-out times, late arrivals and patient categories (senior, child, pregnant, disability). |
| **Check-in by code** | Type or scan the receipt's QR code; the signature is verified before anything is looked up. |
| **Kiosk** | A full-screen self check-in screen that shows only the first name, doctor and time and resets itself. |
| **Walk-ins** | Registration with duplicate detection; an existing record is reused only with the patient's consent. |
| **Queue control** | Call next, start, end, missed turn, returned, arrived (online patients), left without being seen — every change pushed live to patients. |
| **Priority requests** | Ask the patient's doctor to raise a priority, with a reason; the queue changes only when the doctor approves. |
| **Move patients** | Reassign a waiting patient to another doctor in the department or transfer them to another department; they keep their check-in time and get a new token. When a doctor becomes unavailable, their waiting patients can go to colleagues. |
| **Coordination** | Every doctor's queue in a department side by side, with expected finish times, overtime warnings and balancing suggestions confirmed one by one. |
| **Patient records** | Find a patient by name, full mobile number or record number; correct their details with them; see their visits; show the full number when calling (each look is recorded). |
| **Doctor calendar** | Block or reopen slots, record leave (booked patients are told and can rebook free), expected visit length per doctor. |
| **Doctor status** | Breaks, delays, emergencies and "unavailable today" — estimates shift, positions never jump, waiting patients are told. |

### 🩺 For doctors

| Feature | What you get |
| --- | --- |
| **My queue** | Only your own patients: who is in the room, who is waiting with their estimates and categories, and who missed their turn. |
| **Run the room** | Call next, start, end or mark a missed turn, and forward a patient to another doctor or department. |
| **Clinical priority** | Set a patient's priority yourself, and approve or decline the front desk's requests. |
| **Your status** | Record a break, a delay or an emergency; waiting patients are told and keep their place. |

### 📊 For administrators

| Feature | What you get |
| --- | --- |
| **Dashboard** | Booked, waiting, no-shows, left without being seen and doctors away; appointments by department; slot utilization, attendance, no-show and abandonment rates; latency and cost of recent chat turns. |
| **Priority rules** | Choose how much priority seniors, children, pregnant patients and people with a disability get; every open queue is reordered at once. |
| **Analytics in plain language** | Questions answered with one validated, read-only SQL query (shown, with CSV export); requests to change data are refused before any model call. |
| **Registration form** | Add extra registration questions in three languages — asked at sign-up and at the desk, checked by the server. |
| **Evaluation results** | The latest results shipped with the build, each with its sample size. |
| **Hospital setup** | The hospital's name in three languages, address, reception hours and emergency directions; the booking and queue rules (cut-offs, windows, online queue cap); add, edit and remove departments and doctors and their OPD timetables. Changes apply from tomorrow and never cancel a booking; a departing doctor gets a last day and later patients are told and rebook free. |
| **SMS and e-mail** | Turn sending on and choose which kinds of message go out (reminders, changes to a visit, queue updates, waiting-list offers); send a test; see what was sent, what failed and why, and send failed ones again. Providers (Twilio, your own SMS gateway, any SMTP mail server) are set on the server; nothing is sent until an admin turns it on. |
| **Information documents** | Edit, add, translate, hide or restore the documents the library shows and the assistant answers from; rule numbers are placeholders that always match the rules in force. Saved changes are searchable at once. |
| **Accounts** | Create front-desk, doctor, admin and caregiver accounts with a one-time temporary password; switch accounts off and on; reset forgotten passwords. Switching off or resetting ends that person's sessions at once. |
| **Demo reset** | Back to the seed data in one click (people's own accounts and consent are kept; demo deployment only). |

### ♿ Accessibility and languages

- Every screen in **English, हिन्दी and मराठी**, including dates in local formats.
- **Large-text mode** (double size), **44 px tap targets**, full keyboard use and screen-reader labels.
- Checked automatically with **axe-core** on every screen (no serious or critical WCAG A/AA issues) and at
  **360 px** wide in large-text mode.

---

## How it works

```mermaid
flowchart LR
    U["Patient · Front desk · Doctor · Admin<br/>React UI (en / hi / mr)"] -->|HTTPS + WebSocket| API["FastAPI"]
    API --> G{"Emergency check<br/>(rules + classifier)"}
    G -->|emergency| E["Fixed guidance<br/>112 / 108 · no writes"]
    G -->|safe| A["Agent loop<br/>(hand-written tool calling)"]
    A <-->|"Groq → Gemini fallback"| LLM["Language model"]
    A --> T["Tools = business rules<br/>booking · waiting list · queue · permissions"]
    A --> R["Hybrid retrieval<br/>pgvector + BM25 + re-ranker"]
    T --> C["Confirmation card<br/>(preview in a rolled-back savepoint)"]
    T --> DB[("PostgreSQL + pgvector")]
    R --> DB
    Q["Queue engine<br/>+ LightGBM wait model"] --> DB
    Q -->|live updates| API
```

- **Agent** (`app/agent/`) — a hand-written tool-calling loop with argument validation, a step limit, a
  token budget and a masked JSON trace of every model and tool call. Internal ids are removed from replies.
- **Confirmation in code** — a write is first run in a savepoint that is rolled back, so the card shows
  what will really happen; it is executed only after "yes" or a tap on Confirm, and cards expire after
  5 minutes.
- **Retrieval** (`app/rag/`) — 363 documents (121 topics × 3 languages), dense + BM25 search with rank
  fusion, a re-ranker and a relevance threshold. A reply that cites none of the retrieved sources is
  replaced, in code, by "I couldn't find that". Instructions hidden in documents are removed first.
- **Queue and predictions** (`app/queue/`, `app/ml/`) — every event recalculates positions and gives
  each waiting patient an estimate with a range from a LightGBM model trained on 90 simulated days.
  Priority comes from the doctor or from admin-set category rules; moves between doctors, the virtual
  queue and balancing suggestions (a transparent greedy rule) are in the same engine.
- **Providers** — Groq (primary), Gemini (fallback) and Ollama (local) behind one interface.
- **The hospital's data** (`app/tools/`) — accounts, hospital setup and timetables, patient records, rules
  and documents are service functions like the booking rules: role-checked and audited. Rules and
  documents live in the database and apply at once; a document edit is re-indexed in about a second.
- **Background work** — threads in the server send reminders (every 10 minutes), keep 21 days of slots
  open (every 6 hours), close days that are over if the desk did not (every hour: no-shows recorded,
  rebooking offered) and deliver the SMS and e-mail outbox (every 20 seconds).
- **Privacy** — phone numbers and e-mail addresses are encrypted with AES-GCM and masked on every screen,
  log, trace, audit row and model prompt; secrets live only in the environment.
- **Analytics** — reporting views without names or phone numbers, a SELECT-only database role, a SQL
  validator, a read-only transaction and a timeout.

<details>
<summary><b>Tech stack</b></summary>

| Layer | Technology |
| --- | --- |
| API | Python 3.11, FastAPI, SQLAlchemy 2, Alembic, Pydantic |
| Database | PostgreSQL 16 with pgvector (Neon free tier in production) |
| Retrieval | pgvector, BM25 (`rank-bm25`), multilingual embeddings and re-ranker (`fastembed`), local fallbacks (scikit-learn) |
| Prediction | LightGBM |
| Language models | Groq, Gemini, Ollama |
| Analytics guard | sqlglot |
| Privacy and messages | `cryptography` (AES-GCM), scrypt passwords; Twilio, a signed webhook or SMTP for SMS and e-mail |
| UI | React 18, Vite 5, JavaScript, hand-written CSS, lucide-react icons, qrcode |
| Tests | pytest, Vitest, Playwright, axe-core, ruff, ESLint |
| Deployment | Docker, Render (free web service), GitHub Actions |

</details>

---

## Measured results

All numbers come from real runs; details and sample sizes are in [`eval/results/`](eval/results/README.md).

**Safety** (with `groq:openai/gpt-oss-120b`)

| Safety set | Cases | Passed |
| --- | ---: | ---: |
| Emergencies, final held-out set (guidance shown, nothing written) | 60 | **60** · the code gate alone caught 58 |
| Medical-advice bait | 15 | **15** |
| Permission attacks | 15 | **15** |
| Prompt injection (chat and documents) | 15 | **15** |
| Unsafe analytics requests | 10 | **10** |

False alarms on look-alike non-emergencies: **8.3%** (held-out).

**Retrieval and the agent**

| Measure | Result |
| --- | --- |
| Retrieval recall@5 (5-fold cross-validated) | **86.7%** · unchanged after the 6 queue documents (363 documents) |
| Retrieval on 24 new queue questions | **19 / 20** answerable found in the top 5 · 0 / 4 unanswerable left without a source |
| Agent booking scenarios (one run each) | **25 / 25** passed · median turn 0.91 s |
| Queue actions by chat: check in, join online, leave (10 scenarios × 2 runs) | **19 / 20** runs passed · 0 wrong actions · 0 false emergencies |

**Wait-time prediction** (held-out test days)

| Metric | Position × 10 min | Position × doctor average | Model |
| --- | ---: | ---: | ---: |
| Mean absolute error (min) | 29.78 | 29.38 | **17.91** |
| P90 absolute error (min) | 84.88 | 84.07 | **44.20** |
| Range coverage | — | — | **77.7%** (target 75–85%) |

> **Not run yet:** the other 95 of the first 120 agent scenarios, repeat runs, graded RAG answers and the
> comparison with the baseline (the runs were stopped to stay within free quotas). Retrieval numbers are
> for the local retrieval models; the neural models could not be downloaded in the development environment.
> The 25 booking runs used prompt `agent-v2`; the queue-action runs used `agent-v4`. Retrieval was measured
> on the 357-document knowledge base and re-run on the current 363 (`eval/results/rag_kb363.json`). After
> queue requests were added to the emergency gate's training data, the gate alone was re-checked on every
> safety set with the same results (`eval/results/emergency_gate_v3.json`).

---

## Quick start

**With Docker** — you need Docker with Compose and a free Groq or Gemini key for the chat.

```bash
cp .env.example .env        # add GROQ_API_KEY and/or GEMINI_API_KEY
docker compose up --build
```

The container migrates the database, seeds the fictional hospital, loads the knowledge base and serves:

| | |
| --- | --- |
| 🌐 App | <http://localhost:8000> |
| ❤️ Health | <http://localhost:8000/api/v1/health> (`"degraded"` means no model key is set) |
| 📘 API docs | <http://localhost:8000/docs> |

**Demo accounts** (no password): `asha` (patient), `rajan` (caregiver for his father Vinayak), `sunil`
(caregiver not yet verified), `priya` (front desk), `mehta` (admin), `dr-pawar` (doctor; every doctor has a
`dr-<surname>` account) — or create your own account on the start page.

### Running it for a real hospital

Set `DEMO_MODE=false` and choose the first administrator in the environment:

```bash
DEMO_MODE=false
AUTH_SECRET=<a long random value>
INITIAL_ADMIN_USERNAME=admin.sharma
INITIAL_ADMIN_PASSWORD=<a temporary password, 8+ characters>
INITIAL_ADMIN_NAME="Dr. Sharma"
```

At start-up the first admin is created only if no admin can sign in yet, and must choose a new password at the
first sign-in. That admin enters the hospital's details, departments, doctors and OPD timetables under
**Hospital setup**, then creates the front-desk, doctor and other admin accounts under **Accounts**. Each new
account gets a temporary password shown once, which must be replaced at its first sign-in. Patients and
caregivers sign up on the start page or are registered at the desk. With a shell you can also run
`python -m app.manage create-admin --username U --name "…"` or `reset-password --username U`.

> To send reminders and other messages by SMS or e-mail, set `SMS_PROVIDER` and/or `EMAIL_PROVIDER` and their
> keys (see [`docs/DEPLOY.md`](docs/DEPLOY.md#messages-by-sms-and-e-mail)), then turn sending on under
> **SMS and e-mail**. E-mail through any SMTP service is free; SMS cost money.
>
> The information documents start as the demo hospital's (policies with your own rule numbers, but also its
> departments, doctors, facilities and fictional insurers). Review them under **Documents**: edit what applies,
> hide what does not, and add your own.

<details>
<summary><b>Try it from the command line</b></summary>

```bash
# A demo patient
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/demo-login -H 'content-type: application/json' \
  -d '{"role":"patient"}' | python -c "import sys, json; print(json.load(sys.stdin)['token'])")
curl -s -X POST localhost:8000/api/v1/chat -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"message": "Book a Marathi-speaking cardiologist on Saturday"}'
# Reply "yes" with the same conversation_id, or send {"conversation_id": ..., "confirm_action_id": ...}

# Your own account (saved in the database)
curl -s -X POST localhost:8000/api/v1/auth/register -H 'content-type: application/json' \
  -d '{"name":"Kiran Jadhav","username":"kiran","password":"monsoon-tea-7","birth_year":1992,"phone":"9822012345","language":"mr"}'
curl -s -X POST localhost:8000/api/v1/auth/login -H 'content-type: application/json' \
  -d '{"username":"kiran","password":"monsoon-tea-7"}'
```

</details>

**Deploying for free** (Render + Neon): step by step in [`docs/DEPLOY.md`](docs/DEPLOY.md).

---

## Development and tests

You need Python 3.11+, Node 22 and PostgreSQL 16 with pgvector (the Compose `db` service is easiest).

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                       # adjust DATABASE_URL; add a model key for chat

docker compose up -d db
alembic upgrade head
python -m simulator seed                   # the fictional hospital
python -m app.rag.ingest                   # the knowledge base
uvicorn app.api.main:app --reload

cd ui && npm ci && npm run dev             # http://localhost:5173 (proxies /api and /ws to :8000)
```

Without access to Hugging Face, set `EMBEDDING_BACKEND=local` and `RERANKER_BACKEND=local` to use the local
retrieval models straight away.

**Tests** — a real PostgreSQL database; the browser tests run the app with their own database, a fixed clock
and a stand-in language model, so no API key is needed.

```bash
export TEST_DATABASE_URL=postgresql+psycopg://careflow:careflow@localhost:5432/careflow_test
pytest                                     # 461 tests
ruff check . && ruff format --check .
cd ui && npm run lint && npm test && npm run build && cd ..
pytest -m e2e tests/e2e                    # 44 browser tests, including accessibility and 360 px
```

GitHub Actions runs all of these and a Docker build on every push; Render redeploys from `develop`.

<details>
<summary><b>Useful commands</b></summary>

| Command | What it does |
| --- | --- |
| `python -m simulator seed [--if-empty]` | Departments, doctors, demo accounts, 400 synthetic patients, 21 days of slots and bookings |
| `python -m simulator reset` | Demo reset: reload exactly the same seed |
| `python -m simulator replay-day --date YYYY-MM-DD` | Simulate a full OPD day and check its invariants |
| `python -m simulator history --days 90` | Replay past days (training data for the wait-time model) |
| `python -m app.ml.train --end YYYY-MM-DD` | Train and evaluate the wait-time model |
| `python -m simulator.kb.build` | Regenerate the knowledge base from `simulator/kb/` |
| `python -m app.rag.ingest [--if-needed]` | Chunk, embed and load the knowledge base |
| `python -m app.rag.preload` | Download the neural retrieval models |
| `python -m app.manage prepare` | At start-up: demo seed (demo mode only) and the first admin from `INITIAL_ADMIN_*` |
| `python -m app.manage create-admin --username U [--name N]` | A new admin with a temporary password, printed once |
| `python -m app.manage reset-password --username U` | A temporary password for any account, printed once |
| `python -m app.manage new-data-key` | A random `DATA_KEY` for encrypting phone numbers |

</details>

---

## Configuration

<details>
<summary><b>Environment variables</b> (see <code>.env.example</code>)</summary>

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | local Postgres | Postgres connection string (Neon's `postgresql://…` form is accepted) |
| `LLM_PRIMARY`, `LLM_FALLBACK` | `groq:openai/gpt-oss-120b`, `gemini:gemini-3.5-flash-lite` | `provider:model`; providers `groq`, `gemini`, `ollama` |
| `GROQ_API_KEY`, `GEMINI_API_KEY`, `OLLAMA_BASE_URL` | — | Provider credentials / local Ollama address |
| `EMBEDDING_BACKEND`, `RERANKER_BACKEND` | `auto` | `auto`, `local`, or force the neural models |
| `EMBEDDING_MODEL`, `RERANKER_MODEL`, `MODEL_CACHE_DIR` | multilingual MiniLM, bge-reranker-v2-m3 (int8) | Retrieval models and their cache |
| `MAX_MESSAGES_PER_SESSION`, `MAX_MESSAGES_PER_IP_PER_HOUR` | 20, 60 | Chat quota guards |
| `PROMPT_TOKEN_BUDGET`, `RAG_TOP_K` | 3000, 4 | Token budget per agent step; passages given to the model |
| `AUTH_SECRET` | demo value | Signs sign-in tokens and receipt codes — set a long random value when deployed |
| `DATA_KEY` | derived from `AUTH_SECRET` | Encrypts patients' phone numbers (`python -m app.manage new-data-key`); keep it when changing `AUTH_SECRET` |
| `ALLOW_REGISTRATION` | `true` | Let visitors create patient and caregiver accounts |
| `INITIAL_ADMIN_USERNAME`, `INITIAL_ADMIN_PASSWORD`, `INITIAL_ADMIN_NAME` | — | The first admin, created at start-up only if no admin can sign in yet |
| `MAX_REGISTRATIONS_PER_IP_PER_HOUR`, `MAX_FAILED_LOGINS_PER_15_MIN` | 10, 10 | Limits per client address (and username for sign-in) |
| `SMS_PROVIDER`, `EMAIL_PROVIDER` | `none` | Send messages by SMS (`log`, `twilio`, `webhook`) or e-mail (`log`, `smtp`); an admin must also turn sending on. Keys: `TWILIO_*`, `SMS_WEBHOOK_URL`/`_SECRET`, `SMTP_*` ([DEPLOY](docs/DEPLOY.md#messages-by-sms-and-e-mail)) |
| `TRACE_DIR` | `traces` | JSON-lines traces of every turn (masked) |
| `WARM_UP_RETRIEVER` | `true` | Load retrieval at start-up; also starts the slot top-up, reminder and end-of-day threads (the message sender always runs) |
| `QUEUE_MERGE_RULE` | `slot_order` | `slot_order` (booked keep slot order, walk-ins fill gaps) or `alternate` |
| `DEMO_MODE`, `SIMULATOR_SEED` | `true`, `42` | `true`: the fictional hospital, demo roles, demo reset and banner; `false`: a hospital's own deployment. Seed for the synthetic data |

</details>

---

## Business rules

Enforced in code ([`app/tools/policy.py`](app/tools/policy.py)); the booking, rescheduling, cancellation and
waiting-list rules are also stated, with the same numbers, in the hospital's documents.

| Rule | Value |
| --- | --- |
| ✅ Confirmation | Every change needs an explicit yes to a card (5-minute expiry) or a dialog |
| ⚙️ The numbers below | The defaults; each hospital sets its own on the setup page (D-118) |
| 📅 Booking window | From 15 minutes to 30 days ahead |
| 🔁 Rescheduling | Until 12 hours before (any time if the doctor became unavailable) |
| ❌ Cancellation | Until 4 hours before |
| 🚫 Duplicates | One active appointment per patient, doctor and day |
| ⏳ Waiting list | A freed slot is held for the first matching patient for up to 2 hours |
| 📲 Online check-in | From 1 hour before the slot until 15 minutes after it starts |
| 🕒 Late arrival | More than 15 minutes after the slot start → queued by arrival time |
| 📱 Online queue | From 1 hour before OPD opens until 30 minutes before it closes; one queue per patient; at most 10 online patients not yet arrived per doctor |
| ⭐ Priority | Set or approved by the patient's doctor; category priority counts from a booked patient's slot time |
| 🔀 Moving patients | The patient keeps their check-in time and priority and is told the new token |
| 🚑 Emergencies | Guidance (112 / 108) before anything else; nothing is written in that turn |

---

## Project structure

```
app/
  api/        FastAPI app, routes, authentication, rate limits, background threads
  agent/      agent loop, tools, chat service, prompts, model providers, token budget, tracing
  rag/        chunking, embeddings, re-rankers, hybrid retriever, ingestion
  safety/     emergency check, language detection, medical-advice guard, injection filter, masking
  tools/      the business rules: booking, waiting list, calendar, recommendations, reminders,
              accounts, hospital setup and timetables, patient records, documents, policy rules,
              messaging and SMS / e-mail channels,
              receipts, registration and consent, permissions, audit
  queue/      merge rule, queue engine, priority rules, balancing, coordination, live predictions,
              WebSocket broadcaster
  ml/         wait-time features, dataset, model and training (artifacts/ holds the trained model)
  analytics/  analytics agent, read-only SQL guard, utilization
  db/         SQLAlchemy models and sessions
alembic/      database migrations
simulator/    the fictional hospital, seed data, day replay, knowledge-base generator (kb/)
knowledge/    generated knowledge base: <language>/<collection>/<document>.md
eval/         evaluation suites, datasets, run logs and results
ui/           React app: src/pages/ (screens), src/components/, src/i18n.js (all text, 3 languages)
tests/        pytest suite; tests/e2e/ browser tests and the demo recorder
docs/         specification, decisions, deployment guide, screenshots
```

<details>
<summary><b>Requirement traceability</b></summary>

| Requirement | Where | Tests |
| --- | --- | --- |
| FR-01 reply in the user's language | `app/safety/language.py`, `app/agent/messages.py` | `test_safety.py`, s18, s20, s27 |
| FR-02/03 emergency check first, no writes | `app/safety/emergency.py`, `app/agent/chat.py` | `test_safety.py`, s19–s21 |
| FR-04 no diagnosis or medicines | `app/safety/output_guard.py`, prompt | s24, `test_safety.py` |
| FR-05 ask for missing information | system prompt | evaluation |
| FR-06 human handoff | `app/tools/handoff.py`, `app/agent/chat.py` | s22, s23 |
| FR-07/08 doctors and slots | `app/tools/booking.py` | `test_booking.py`, `test_api.py` |
| FR-09 confirmation before booking | `app/agent/tools.py` (preview → card), `app/agent/chat.py` | TC-01, s01–s07 |
| FR-10/11 taken slots, duplicates | row lock + partial unique indexes | TC-02–TC-04, s06, s08 |
| FR-12/13 reschedule / cancel windows | `app/tools/booking.py` | TC-05, TC-06, s09–s11 |
| FR-14 waiting list | `app/tools/waiting_list.py` | TC-07, s12 |
| FR-15 caregivers | `app/tools/permissions.py`, `app/tools/registration.py` | TC-08, s13, s14, `test_registration.py` |
| FR-16 history | `get_patient_appointments` | `test_booking.py`, `test_api.py` |
| FR-17–20 knowledge base, citations, "I don't know" | `app/rag/`, `app/agent/loop.py` | s16–s18, `test_knowledge.py` |
| FR-21–28 queue, estimates, live push | `app/queue/`, `app/ml/`, `/ws/queue/{id}` | `test_queue*.py`, `test_wait_time.py`, TC-09–TC-13, TC-20 |
| FR-29–32 dashboard, analytics, evaluation | `app/api/admin_routes.py`, `app/analytics/` | TC-14, TC-15, `test_admin_api.py`, `test_analytics.py` |
| FR-33 audit log | `app/tools/audit.py` | TC-16 |
| FR-34 demo reset | `simulator/seed.py` | TC-17 |
| Phase 6A appointment features | `app/tools/{calendar,recommend,reminders,receipts}.py`, `app/api/care_routes.py` | `test_care_features.py`, e2e |
| Phase 6B registration and check-in | `app/tools/registration.py`, `app/api/registration_routes.py` | `test_registration.py`, `test_queue.py`, e2e |
| Phase 6C queue management | `app/queue/{engine,balance,coordination,rules}.py`, `app/api/queue_routes.py` | `test_queue_management*.py`, `test_balance.py`, `test_merge.py`, e2e |
| FR-58–61, 69 production mode and accounts | `app/tools/accounts.py`, `app/api/accounts_routes.py`, `app/manage.py` | `test_account_management.py`, `test_accounts.py`, e2e |
| FR-62–64 hospital setup and timetables | `app/tools/{hospital,timetable}.py`, `app/api/setup_routes.py` | `test_hospital_setup.py`, e2e |
| FR-65–68 patient data | `app/safety/pii.py`, `app/tools/patients.py`, `app/api/patients_routes.py` | `test_patient_data.py`, `test_audit_privacy.py`, e2e |
| FR-70/71 rules and documents | `app/tools/{policy,policy_settings,documents}.py`, `app/rag/kb.py` | `test_documents_admin.py`, e2e |
| FR-72–74 SMS and e-mail | `app/tools/{messaging,channels,notify}.py`, `app/api/messaging_routes.py` | `test_messaging.py`, e2e |
| NFR-06 MAE below both baselines | `app/ml/train.py` | `eval/results/ml_wait_time.json` |
| NFR-07 roles in tools | every service function | `test_permissions.py`, s14, s15 |
| NFR-08 masking | `app/safety/privacy.py`, traces | TC-18, s29 |
| NFR-09–11 quotas, token budget, fallback | `app/api/routes.py`, `app/agent/budget.py`, `app/agent/llm.py` | `test_api.py`, `test_llm.py`, TC-19 |
| NFR-12/13 phone, large text, accessibility | `ui/src/styles.css` | e2e (axe-core, 360 px) |
| NFR-14 tracing | `app/agent/tracing.py` | s29 |
| NFR-17 encryption at rest | `app/safety/pii.py` | `test_patient_data.py`, `test_messaging.py` |

</details>

---

## Limitations

- **Measured on synthetic data.** The demo and the evaluation use the simulated hospital, whose parameters are
  assumptions ([`docs/DECISIONS.md`](docs/DECISIONS.md), D-21); the wait-time model learned from simulated days
  whose queues are short.
- **Real use** (D-99): accounts, production mode, hospital setup, patient records (encryption, correction,
  export, erasure), editable documents and rules, and messages by SMS and e-mail are in place. After documents are edited, new words are found by keyword search at once and by the dense
  embeddings after the next deployment (D-121).
  Department names are shown as entered, in one language.
- **Chat and real patient data** (D-117): chat messages (numbers masked), patient names and appointment details
  go to the configured LLM provider. A hospital must decide whether that is acceptable, use a provider it has an
  agreement with, or run a local model with Ollama.
- **Evaluation is incomplete** (see [Measured results](#measured-results)); retrieval was measured with the local
  models, which handle Marathi inflections less well than the neural ones.
- **Messages** — sent by SMS or e-mail only once a hospital sets up a provider and turns sending on (never in
  the demo). Reminders are in the patient's language; the other notices are in English. Indian commercial SMS
  need DLT registration through the hospital's provider. While the free server sleeps, messages wait (D-123).
- **Accounts** have no e-mail or SMS verification and no self-service password reset; an admin resets a
  forgotten password with a temporary one.
- **One process** — the live WebSocket broadcaster runs in a single process; several servers would need a
  shared message bus.
- **Free hosting** — the Render free instance sleeps after 15 idle minutes; the first visit then takes
  about a minute. Free model quotas can make the assistant briefly busy.

---

## Documentation

| Document | Contents |
| --- | --- |
| [`docs/CareFlow-Project-Documentation.md`](docs/CareFlow-Project-Documentation.md) | The specification (version 2.0): problem, requirements (FR-01–FR-74), architecture, database, API, screens, tests, roadmap, security, operations, risks and evaluation |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Every decision, phase by phase (D-00a to D-130), with the reason |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | Free deployment on Render and Neon, monitoring and runbook |
| [`eval/README.md`](eval/README.md) | How the evaluation works and how to run it |
| [`eval/results/README.md`](eval/results/README.md) | The generated results table with sample sizes |

<div align="center">
<sub>Indravani General Hospital and everyone in it (the demo) are fictional. CareFlow helps run an OPD; it is not a medical device and gives no medical advice.</sub>
</div>
