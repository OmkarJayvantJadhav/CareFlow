<div align="center">

<img src="docs/gifs/homepage.gif" alt="A hospital's homepage built with CareFlow: departments, doctors, hours and an emergency strip" width="100%">

# 🏥 CareFlow

### See your doctor without the long wait

**Book a doctor's appointment, get answers about the hospital and see when it's your turn —<br>in English, हिन्दी and मराठी.**

<br>

[![Live demo](https://img.shields.io/badge/▶%20try%20the%20live%20demo-careflow--zy87.onrender.com-0f766e?style=for-the-badge)](https://careflow-zy87.onrender.com)
&nbsp;
[![Hospital site](https://img.shields.io/badge/🏥%20hospital%20site-omkar--general--hospital-1e40af?style=for-the-badge)](https://omkar-general-hospital.onrender.com)

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.148-009688?logo=fastapi&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-4169E1?logo=postgresql&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![Vite](https://img.shields.io/badge/Vite-5-646CFF?logo=vite&logoColor=white)
![LightGBM](https://img.shields.io/badge/LightGBM-wait%20times-9ACD32)
![Docker](https://img.shields.io/badge/Docker-Render%20%2B%20Neon-2496ED?logo=docker&logoColor=white)
<br>
![Tests](https://img.shields.io/badge/tests-473%20Python%20·%2045%20browser%20·%2013%20UI-15803d)
![Accessibility](https://img.shields.io/badge/WCAG-A%2FAA%20checked-1e40af)
![Languages](https://img.shields.io/badge/languages-English%20·%20हिन्दी%20·%20मराठी-f97316)

<br>

**[In plain words](#-careflow-in-plain-words)** &nbsp;·&nbsp;
**[Features](#-features-in-action)** &nbsp;·&nbsp;
**[How it works](#️-how-it-works)** &nbsp;·&nbsp;
**[Results](#-measured-results)** &nbsp;·&nbsp;
**[Quick start](#-quick-start)** &nbsp;·&nbsp;
**[Real hospital](#-running-it-for-a-real-hospital)** &nbsp;·&nbsp;
**[Docs](#-documentation)**

</div>

<br>

> [!NOTE]
> **Portfolio project.** Both sites run a fictional hospital, "Omkar General Hospital", with synthetic data — not
> a real hospital and not for medical use. The **demo** lets you try every role without an account; the
> **hospital site** (`DEMO_MODE=false`) is how a real hospital would run it, with its own homepage, accounts,
> departments, doctors, rules and documents.

<br>

<div align="center">

| 🚑 Emergencies caught | 🔎 Right passage found | ⏱️ Wait-time error | 🛡️ Attacks resisted | 🤖 Booking scenarios |
| :---: | :---: | :---: | :---: | :---: |
| **60 / 60**<br><sub>held-out set, before the model</sub> | **85.9%**<br><sub>recall@5, cross-validated</sub> | **17.9 min**<br><sub>vs 29.4 min baseline</sub> | **15 / 15**<br><sub>prompt-injection tests</sub> | **25 / 25**<br><sub>agent runs passed</sub> |

</div>

---

## 🙋 CareFlow in plain words

<table>
  <tr>
    <td width="25%" valign="top" align="center">
      <h3>🧑‍⚕️</h3>
      <b>Patients and families</b><br><br>
      Book a time with a doctor — by chatting or by picking a slot — check in from your phone, and see how
      many people are ahead of you and how long you'll wait.
    </td>
    <td width="25%" valign="top" align="center">
      <h3>🗂️</h3>
      <b>Reception desk</b><br><br>
      Check patients in, add walk-ins and call the next patient. Every patient's phone updates at once.
    </td>
    <td width="25%" valign="top" align="center">
      <h3>🩺</h3>
      <b>Doctors</b><br><br>
      See only your own patients: who is in the room, who is next, and requests from the desk.
    </td>
    <td width="25%" valign="top" align="center">
      <h3>🏛️</h3>
      <b>Hospital admins</b><br><br>
      Set up departments, doctors and timings, staff accounts, booking rules and the information patients
      read.
    </td>
  </tr>
</table>

It works on a phone or a computer, and the assistant **never books, changes or cancels anything until you tap
Confirm**.

---

## ✨ Why CareFlow

Outpatient clinics lose hours to phone queues, double bookings and crowded waiting rooms. CareFlow puts the
whole visit in one place, built on four principles:

<table>
  <tr>
    <td width="50%" valign="top">
      <h4>🛡️ Rules live in code, not in the model</h4>
      The language model can only <i>propose</i> a change. CareFlow checks it, shows a confirmation card and acts
      only on an explicit "yes". Booking windows, duplicates and permissions are enforced in every tool.
    </td>
    <td width="50%" valign="top">
      <h4>🚑 Safety first</h4>
      Every message is checked for emergencies <i>before</i> the model sees it. An emergency gets fixed guidance
      (call 112 / 108) and nothing is written. Medicine names and doses never reach the user.
    </td>
  </tr>
  <tr>
    <td valign="top">
      <h4>🏥 The hospital's own</h4>
      Nothing about the hospital is hardcoded: admins manage accounts, departments, doctors, timetables, rules,
      documents and messages. Contact details are encrypted; patients can download or erase their data.
    </td>
    <td valign="top">
      <h4>📏 Measured, not assumed</h4>
      An evaluation suite with held-out sets measures safety, retrieval and the agent. Every number in this
      README comes from a real run and states its sample size.
    </td>
  </tr>
</table>

---

## 🎬 Features in action

Every clip is the real app, recorded by a browser script ([`tests/e2e/record_gifs.py`](tests/e2e/record_gifs.py));
the chat uses the test server's rule-based stand-in for the language model so the clips are repeatable.

### 🧑‍⚕️ For patients and families

#### 💬 Book by chat — with a confirmation card

Ask in plain language. The assistant finds the doctor and time, then shows exactly what will happen; nothing
changes until you tap **Confirm** (cards expire after 5 minutes). Reschedule, cancel, join a waiting list, check
in or join a queue the same way — or tap **Talk to a person**.

<img src="docs/gifs/chat-booking.gif" alt="Booking a Marathi-speaking cardiologist by chat, confirming the card and seeing it in My appointments" width="100%">

<table>
  <tr>
    <td width="50%" valign="top">
      <h4>📚 Answers with sources</h4>
      Policies, insurance, test preparation and facilities come from the hospital's own documents, with source
      chips that open the passage. When the documents don't say, the assistant says so.
      <br><br>
      <img src="docs/gifs/cited-answer.gif" alt="Asking about fasting before a lipid profile and opening the cited source" width="100%">
    </td>
    <td width="50%" valign="top">
      <h4>🚑 Emergencies come first</h4>
      "My father collapsed" never reaches the model: a fixed panel with 112 / 108 takes over the chat, and
      nothing is booked or changed.
      <br><br>
      <img src="docs/gifs/emergency.gif" alt="An emergency message replaced by the emergency guidance panel" width="100%">
    </td>
  </tr>
  <tr>
    <td valign="top">
      <h4>📅 Book without chatting</h4>
      Pick a department, doctor, language, dates and time of day. Each suggestion says why — <i>Soonest</i>,
      <i>Speaks your language</i>, <i>Doctor you have seen</i>, <i>Quieter day</i> — and every booking gets a
      printable receipt with a signed QR code.
      <br><br>
      <img src="docs/gifs/book-and-receipt.gif" alt="Finding ranked ENT times, confirming a booking and opening the receipt with its QR code" width="100%">
    </td>
    <td valign="top">
      <h4>⏱️ Check in and watch the live queue</h4>
      Check in from an hour before the slot; your token appears at once. The queue page shows people ahead and
      "about 65 min (60–100)", pushed over a WebSocket in under 2 seconds.
      <br><br>
      <img src="docs/gifs/check-in-live-queue.gif" alt="Checking in from My appointments, then the queue page updating live when the doctor runs late" width="100%">
    </td>
  </tr>
  <tr>
    <td valign="top">
      <h4>📱 Join a doctor's queue online</h4>
      No appointment? Join today's queue from your phone, come in when your turn is near, or leave if plans
      change. Caregivers do it for the family members they look after.
      <br><br>
      <img src="docs/gifs/join-queue-online.gif" alt="A caregiver joining an ENT doctor's queue online and getting token V01" width="100%">
    </td>
    <td valign="top">
      <h4>📖 Hospital information for everyone</h4>
      All 121 topics the assistant answers from, in three languages, searchable without signing in.
      <br><br>
      <img src="docs/gifs/hospital-information.gif" alt="Searching the hospital information, opening a document and switching it to Hindi and Marathi" width="100%">
    </td>
  </tr>
  <tr>
    <td valign="top">
      <h4>🌐 English, हिन्दी and मराठी everywhere</h4>
      Every screen, date and message in the patient's language.
      <br><br>
      <img src="docs/gifs/languages.gif" alt="Switching the whole interface between English, Hindi and Marathi" width="100%">
    </td>
    <td valign="top">
      <h4>🔐 Profile, privacy and caregivers</h4>
      Edit your details and password, choose SMS, e-mail or in-app messages, approve caregivers, download all
      your data or delete your account.
      <br><br>
      <img src="docs/gifs/profile-privacy.gif" alt="Approving a caregiver's request on the profile page" width="100%">
    </td>
  </tr>
</table>

<table>
  <tr>
    <td width="38%" align="center"><img src="docs/gifs/phone.gif" alt="CareFlow on a phone: joining a queue by chat, the live token and My appointments" width="290"></td>
    <td width="62%" valign="middle">
      <h3>📲 Made for phones</h3>
      <ul>
        <li>Four bottom tabs and a <b>More</b> menu that lists every other page by its full name</li>
        <li>Table rows become labelled cards; words never break apart</li>
        <li>Large-text mode and 44 px tap targets</li>
        <li>Every screen checked automatically at 360 px wide in large text, and with <b>axe-core</b> for WCAG A/AA</li>
      </ul>
    </td>
  </tr>
</table>

### 🗂️ For the front desk and doctors

#### 🧾 The front desk's day

Every doctor on duty with bookings, check-ins, late arrivals and patient categories. Check in by receipt code or
QR, register walk-ins (duplicates are detected), and run the queue — call next, start, end, missed turn — with
every change pushed live to patients.

<img src="docs/gifs/front-desk.gif" alt="Checking in a booked patient, registering a walk-in and calling the next patient" width="100%">

<table>
  <tr>
    <td width="33%" valign="top">
      <h4>🖥️ Self check-in kiosk</h4>
      Type or scan the receipt code, see only your first name, check in — and it resets itself.
      <br><br>
      <img src="docs/gifs/kiosk.gif" alt="A patient checking in at the kiosk with their receipt code" width="100%">
    </td>
    <td width="33%" valign="top">
      <h4>🩺 The doctor's own queue</h4>
      Approve priority requests, call, start and end visits, forward patients and record breaks or delays.
      <br><br>
      <img src="docs/gifs/doctor-queue.gif" alt="A doctor approving a priority request, calling the patient and ending the visit" width="100%">
    </td>
    <td width="33%" valign="top">
      <h4>⚖️ Coordination across doctors</h4>
      A department's queues side by side, with balancing moves suggested and confirmed one by one.
      <br><br>
      <img src="docs/gifs/coordination.gif" alt="The cardiology coordination board suggesting and making a balancing move" width="100%">
    </td>
  </tr>
</table>

### 🏛️ For hospital admins

#### 📈 Dashboard and analytics in plain language

Today's numbers, utilization, attendance and no-show rates, and the latest evaluation results. Questions in plain
language are answered with one validated, read-only SQL query — shown, with CSV export; requests to change data
are refused before any model call.

<img src="docs/gifs/dashboard-analytics.gif" alt="The hospital dashboard, then an analytics question answered with a table and the generated SQL" width="100%">

<table>
  <tr>
    <td width="50%" valign="top">
      <h4>🏗️ Hospital setup</h4>
      Name and address in three languages, reception hours, emergency directions, booking and queue rules,
      departments, doctors and their timetables. Changes apply from tomorrow and never cancel a booking. On a
      hospital's own site the department, doctor, floor-guide, hours, location and emergency pages are written
      from this setup and update by themselves.
      <br><br>
      <img src="docs/gifs/hospital-setup.gif" alt="Adding a Neurology department and a doctor" width="100%">
    </td>
    <td width="50%" valign="top">
      <h4>📝 Information documents</h4>
      Edit, add, translate, hide or restore what the library shows and the assistant cites. Rule numbers are
      placeholders such as <code>{{cancel_hours}}</code>, so the documents always match the rules in force.
      <br><br>
      <img src="docs/gifs/documents.gif" alt="Opening the cancellation policy in the document editor with its placeholders" width="100%">
    </td>
  </tr>
  <tr>
    <td valign="top">
      <h4>👥 Accounts</h4>
      Front-desk, doctor and admin accounts with a one-time temporary password that must be replaced at first
      sign-in. Switch accounts off and on, or reset a forgotten password.
      <br><br>
      <img src="docs/gifs/accounts.gif" alt="Creating a front-desk account and seeing its temporary password once" width="100%">
    </td>
    <td valign="top">
      <h4>✉️ SMS and e-mail</h4>
      Off until an admin turns it on. Choose which messages go out, send a test, and see what was sent or failed.
      Twilio, your own SMS gateway or any SMTP server.
      <br><br>
      <img src="docs/gifs/messaging.gif" alt="Turning on SMS and e-mail and sending a test message" width="100%">
    </td>
  </tr>
</table>

<details>
<summary><b>📋 Every feature, in one list</b></summary>
<br>

| Who | Features |
| --- | --- |
| **Patients and caregivers** | Assistant chat with confirmation cards and "Talk to a person" · booking with ranked, explained times · cited answers · hospital information without signing in · My appointments (receipt, reschedule, cancel, rebook) · signed QR receipts · online check-in · joining a queue online · live queue with estimate and range · reminders in the app, by SMS or e-mail · profile, consent, caregivers, data download and account deletion · the hospital's homepage |
| **Front desk** | Today at a glance · check-in by code or QR · kiosk · walk-ins with duplicate detection · queue control · priority requests to the doctor · moving patients between doctors and departments · coordination and balancing · patient records (masked numbers, each look recorded) · doctor calendar and leave · doctor status (break, delay, emergency, unavailable) |
| **Doctors** | Own queue · call, start, end, missed turn, forward · clinical priority and approving requests · own status |
| **Administrators** | Dashboard · priority rules by patient category · analytics in plain language · registration questions · evaluation results · hospital setup and timetables · booking and queue rules · SMS and e-mail · information documents · accounts · demo reset (demo only) |
| **Everyone** | English, हिन्दी and मराठी · large-text mode · 44 px tap targets · keyboard and screen-reader support · checked with axe-core and at 360 px |

</details>

---

## ⚙️ How it works

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

| Part | What it does | Where |
| --- | --- | --- |
| 🤖 **Agent** | A hand-written tool-calling loop with argument validation, a step limit, a token budget and a masked JSON trace of every model and tool call; internal ids are removed from replies | `app/agent/` |
| ✅ **Confirmation in code** | A write first runs in a savepoint that is rolled back, so the card shows what will really happen; it runs for real only after "yes" or **Confirm**, and cards expire after 5 minutes | `app/agent/tools.py` |
| 🔎 **Retrieval** | 363 documents (121 topics × 3 languages): dense + BM25 search with rank fusion, a re-ranker and a relevance threshold. A reply citing none of the retrieved sources is replaced, in code, by "I couldn't find that"; instructions hidden in documents are removed first | `app/rag/` |
| ⏱️ **Queue and predictions** | Every event recalculates positions and gives each waiting patient an estimate with a range from a LightGBM model trained on 90 simulated days; priorities, moves, the online queue and balancing (a transparent greedy rule) share one engine | `app/queue/`, `app/ml/` |
| 🔌 **Providers** | Groq (primary), Gemini (fallback) and Ollama (local) behind one interface | `app/agent/llm.py` |
| 🏥 **The hospital's data** | Accounts, setup and timetables, patient records, rules and documents are role-checked, audited service functions; rules and documents live in the database and apply at once (a document edit is re-indexed in about a second) | `app/tools/` |
| 🔁 **Background work** | Reminders (every 10 min) · 21 days of slots kept open (6 h) · days that are over closed, no-shows recorded, rebooking offered and the hospital's own department and doctor pages refreshed (1 h) · lapsed waiting-list offers passed on (5 min) · the SMS and e-mail outbox (20 s) | `app/api/main.py` |
| 🔐 **Privacy** | Phone numbers and e-mail addresses encrypted with AES-GCM and masked on every screen, log, trace, audit row and model prompt; secrets live only in the environment | `app/safety/` |
| 📊 **Analytics** | Reporting views without names or phone numbers, a SELECT-only database role, a SQL validator, a read-only transaction and a timeout | `app/analytics/` |

<details>
<summary><b>🧰 Tech stack</b></summary>
<br>

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

## 📏 Measured results

All numbers come from real runs; details and sample sizes are in [`eval/results/`](eval/results/README.md).

<table>
  <tr>
    <td width="50%" valign="top">

**🛡️ Safety** <sub>(with `groq:openai/gpt-oss-120b`)</sub>

| Safety set | Cases | Passed |
| --- | ---: | ---: |
| Emergencies, final held-out set | 60 | **60** |
| Medical-advice bait | 15 | **15** |
| Permission attacks | 15 | **15** |
| Prompt injection (chat and documents) | 15 | **15** |
| Unsafe analytics requests | 10 | **10** |

<sub>The code gate alone caught 58 of the 60 emergencies. False alarms on look-alike non-emergencies: 8.3% (held-out).</sub>

  </td>
  <td width="50%" valign="top">

**⏱️ Wait-time prediction** <sub>(held-out test days)</sub>

| Metric | Position × 10 min | Position × doctor avg | Model |
| --- | ---: | ---: | ---: |
| Mean abs. error (min) | 29.78 | 29.38 | **17.91** |
| P90 abs. error (min) | 84.88 | 84.07 | **44.20** |
| Range coverage | — | — | **77.7%** |

<sub>Coverage target: 75–85%.</sub>

  </td>
  </tr>
</table>

**🔎 Retrieval and the agent**

| Measure | Result |
| --- | --- |
| Retrieval recall@5 (5-fold cross-validated) | **85.9%** on the current 363 documents · 86.7% before the privacy document was rewritten (one question changed) |
| Retrieval on 24 new queue questions | **18 / 20** answerable found in the top 5 (19 / 20 before the documents were renamed, D-132) · 0 / 4 unanswerable left without a source |
| Agent booking scenarios (one run each) | **25 / 25** passed · median turn 0.91 s |
| Queue actions by chat: check in, join online, leave (10 scenarios × 2 runs) | **19 / 20** runs passed · 0 wrong actions · 0 false emergencies |

> [!IMPORTANT]
> **Not run yet:** the other 95 of the first 120 agent scenarios, repeat runs, graded RAG answers and the
> comparison with the baseline (the runs were stopped to stay within free quotas). Retrieval numbers are for the
> local retrieval models; the neural models could not be downloaded in the development environment. The 25
> booking runs used prompt `agent-v2`; the queue-action runs used `agent-v4`. Retrieval was measured on the
> 357-document knowledge base and re-run on the current 363 (`eval/results/rag_kb363_omkar.json`). After queue
> requests were added to the emergency gate's training data, the gate alone was re-checked on every safety set
> with the same results (`eval/results/emergency_gate_v3.json`).

---

## 🚀 Quick start

> [!TIP]
> The fastest way to look around is the **[live demo](https://careflow-zy87.onrender.com)**: pick a role and go,
> no account needed. It sleeps when idle, so the first visit can take about a minute.

**Run it locally with Docker** — you need Docker with Compose and a free Groq or Gemini key for the chat.

```bash
cp .env.example .env        # add GROQ_API_KEY and/or GEMINI_API_KEY
docker compose up --build
```

The container migrates the database, seeds the fictional hospital, loads the knowledge base and serves:

| | |
| --- | --- |
| 🌐 **App** | <http://localhost:8000> |
| ❤️ **Health** | <http://localhost:8000/api/v1/health> (`"degraded"` means no model key is set) |
| 📘 **API docs** | <http://localhost:8000/docs> |

**Demo accounts** (no password):

| Username | Role |
| --- | --- |
| `asha` | Patient |
| `rajan` | Caregiver for his father Vinayak |
| `sunil` | Caregiver not yet verified |
| `priya` | Front desk |
| `mehta` | Hospital admin |
| `dr-pawar` | Doctor (every doctor has a `dr-<surname>` account) |

Or create your own account on the start page.

<details>
<summary><b>💻 Try it from the command line</b></summary>
<br>

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

## 🏥 Running it for a real hospital

Set `DEMO_MODE=false` and choose the first administrator in the environment:

```bash
DEMO_MODE=false
AUTH_SECRET=<a long random value>
INITIAL_ADMIN_USERNAME=admin.sharma
INITIAL_ADMIN_PASSWORD=<a temporary password, 8+ characters>
INITIAL_ADMIN_NAME="Dr. Sharma"
```

| Step | What happens |
| :---: | --- |
| **1** | At start-up the first admin is created (only if no admin can sign in yet) and must choose a new password at the first sign-in |
| **2** | The admin enters the hospital's details, departments, doctors and timetables under **Hospital setup** — the department, doctor, floor-guide, hours, location and emergency pages are written from it in all three languages |
| **3** | The admin creates front-desk, doctor and other admin accounts under **Accounts**; each gets a temporary password shown once |
| **4** | Patients and caregivers sign up at `/login` or are registered at the desk; visitors land on the hospital's homepage at `/` |
| **5** | Under **Documents**, the admin reviews the remaining demo documents (policies already use the hospital's own rule numbers; facilities and insurers are the demo's) — edit, hide or add |

With a shell you can also run `python -m app.manage create-admin --username U --name "…"` or
`reset-password --username U`.

> [!NOTE]
> To send reminders and other messages by SMS or e-mail, set `SMS_PROVIDER` and/or `EMAIL_PROVIDER` and their
> keys (see [`docs/DEPLOY.md`](docs/DEPLOY.md#messages-by-sms-and-e-mail)), then turn sending on under
> **SMS and e-mail**. E-mail through any SMTP service is free; SMS cost money.

---

## 🧪 Development and tests

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

**Tests** — a real PostgreSQL database; the browser tests run the app with their own database, a fixed clock and a
stand-in language model, so no API key is needed.

```bash
export TEST_DATABASE_URL=postgresql+psycopg://careflow:careflow@localhost:5432/careflow_test
pytest                                     # 473 tests
ruff check . && ruff format --check .
cd ui && npm run lint && npm test && npm run build && cd ..
pytest -m e2e tests/e2e                    # 45 browser tests, including accessibility and 360 px
```

GitHub Actions runs all of these and a Docker build on every push; Render redeploys from `develop`.

<details>
<summary><b>🛠️ Useful commands</b></summary>
<br>

| Command | What it does |
| --- | --- |
| `python -m simulator seed [--if-empty]` | Departments, doctors, demo accounts, 400 synthetic patients, 21 days of slots and bookings |
| `python -m simulator reset` | Demo reset: reload exactly the same seed |
| `python -m simulator replay-day --date YYYY-MM-DD` | Simulate a full clinic day and check its invariants |
| `python -m simulator history --days 90` | Replay past days (training data for the wait-time model) |
| `python -m app.ml.train --end YYYY-MM-DD` | Train and evaluate the wait-time model |
| `python -m simulator.kb.build` | Regenerate the knowledge base from `simulator/kb/` |
| `python -m app.rag.ingest [--if-needed]` | Chunk, embed and load the knowledge base |
| `python -m app.rag.preload` | Download the neural retrieval models |
| `python -m app.manage prepare` | At start-up: demo seed (demo mode only) and the first admin from `INITIAL_ADMIN_*` |
| `python -m app.manage create-admin --username U [--name N]` | A new admin with a temporary password, printed once |
| `python -m app.manage reset-password --username U` | A temporary password for any account, printed once |
| `python -m app.manage new-data-key` | A random `DATA_KEY` for encrypting phone numbers |
| `python -m tests.e2e.record_gifs [name …]` | Re-record the README's GIFs into `docs/gifs/` (needs ffmpeg and a built UI) |

</details>

<details>
<summary><b>🔧 Environment variables</b> (see <code>.env.example</code>)</summary>
<br>

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
| `DEMO_SITE_URL` | — | A hospital's own deployment: show "Try the demo" on the homepage (top and footer) and the sign-in page, linking to this demo site |
| `DEMO_NOTICE` | `true` | In demo mode, say on every page that the hospital is fictional; `false` keeps the try-a-role buttons without labels (the live site) |
| `DEMO_MODE`, `SIMULATOR_SEED` | `true`, `42` | `true`: the fictional hospital, demo roles, demo reset and banner; `false`: a hospital's own deployment. Seed for the synthetic data |

</details>

---

## 📜 Business rules

Enforced in code ([`app/tools/policy.py`](app/tools/policy.py)); the booking, rescheduling, cancellation and
waiting-list rules are also stated, with the same numbers, in the hospital's documents. The numbers are the
defaults — each hospital sets its own on the setup page (D-118).

<table>
  <tr>
    <td width="50%" valign="top">

| Rule | Value |
| --- | --- |
| ✅ Confirmation | Explicit yes to a card (5-min expiry) or dialog |
| 📅 Booking window | 15 minutes to 30 days ahead |
| 🔁 Rescheduling | Until 12 h before (any time if the doctor became unavailable) |
| ❌ Cancellation | Until 4 h before |
| 🚫 Duplicates | One active appointment per patient, doctor and day |
| ⏳ Waiting list | A freed slot is held for the first match for up to 2 h |

  </td>
  <td width="50%" valign="top">

| Rule | Value |
| --- | --- |
| 📲 Online check-in | 1 h before the slot to 15 min after it starts |
| 🕒 Late arrival | > 15 min after the slot → queued by arrival time |
| 📱 Online queue | 1 h before clinic hours until 30 min before they end; at most 10 online patients not yet arrived per doctor |
| ⭐ Priority | Set or approved by the patient's doctor |
| 🔀 Moving patients | Keeps check-in time and priority; new token |
| 🚑 Emergencies | 112 / 108 guidance first; nothing written that turn |

  </td>
  </tr>
</table>

---

## 🗂️ Project structure

```
app/
  api/        FastAPI app, routes, authentication, rate limits, background threads
  agent/      agent loop, tools, chat service, prompts, model providers, token budget, tracing
  rag/        chunking, embeddings, re-rankers, hybrid retriever, ingestion, pages written from the setup
  safety/     emergency check, language detection, medical-advice guard, injection filter, masking
  tools/      the business rules: booking, waiting list, calendar, recommendations, reminders,
              accounts, hospital setup and timetables, patient records, documents, policy rules,
              messaging and SMS / e-mail channels, receipts, registration and consent, permissions, audit
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
tests/        pytest suite; tests/e2e/ browser tests and the GIF recorder
docs/         specification, decisions, deployment guide, gifs/ (the README's clips)
```

<details>
<summary><b>🧭 Requirement traceability</b></summary>
<br>

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
| FR-62–64 hospital setup and timetables | `app/tools/{hospital,timetable}.py`, `app/api/setup_routes.py`, `app/rag/setup_docs.py` | `test_hospital_setup.py`, `test_setup_documents.py`, e2e |
| FR-65–68 patient data | `app/safety/pii.py`, `app/tools/patients.py`, `app/api/patients_routes.py` | `test_patient_data.py`, `test_audit_privacy.py`, e2e |
| FR-70/71 rules and documents | `app/tools/{policy,policy_settings,documents}.py`, `app/rag/kb.py` | `test_documents_admin.py`, e2e |
| FR-72–74 SMS and e-mail | `app/tools/{messaging,channels,notify}.py`, `app/api/messaging_routes.py` | `test_messaging.py`, e2e |
| NFR-06 MAE below both baselines | `app/ml/train.py` | `eval/results/ml_wait_time.json` |
| NFR-07 roles in tools | every service function | `test_permissions.py`, s14, s15 |
| NFR-08 masking | `app/safety/privacy.py`, traces | TC-18, s29 |
| NFR-09–11 quotas, token budget, fallback | `app/api/routes.py`, `app/agent/budget.py`, `app/agent/llm.py` | `test_api.py`, `test_llm.py`, TC-19 |
| NFR-12/13 phone, large text, accessibility | `ui/src/styles.css`, `ui/src/components/` | e2e (axe-core, 360 px) |
| NFR-14 tracing | `app/agent/tracing.py` | s29 |
| NFR-17 encryption at rest | `app/safety/pii.py` | `test_patient_data.py`, `test_messaging.py` |

</details>

---

## ⚠️ Limitations

| | |
| --- | --- |
| 🧪 **Synthetic data** | The demo and the evaluation use the simulated hospital, whose parameters are assumptions ([`docs/DECISIONS.md`](docs/DECISIONS.md), D-21); the wait-time model learned from simulated days whose queues are short |
| 🔎 **Search after edits** | After documents are edited, new words are found by keyword search at once and by the dense embeddings after the next deployment (D-121). Department names are shown as entered, in one language |
| 🤖 **Chat and patient data** | Chat messages (numbers masked), patient names and appointment details go to the configured LLM provider (D-117). A hospital must decide whether that is acceptable, use a provider it has an agreement with, or run a local model with Ollama |
| 📏 **Evaluation is incomplete** | See [Measured results](#-measured-results); retrieval was measured with the local models, which handle Marathi inflections less well than the neural ones |
| ✉️ **Messages** | Sent by SMS or e-mail only once a hospital sets up a provider and turns sending on (never in the demo). Reminders are in the patient's language; the other notices are in English. Indian commercial SMS need DLT registration. While the free server sleeps, messages wait (D-123) |
| 🔑 **Accounts** | No e-mail or SMS verification and no self-service password reset; an admin resets a forgotten password with a temporary one |
| 🖥️ **One process** | The live WebSocket broadcaster runs in a single process; several servers would need a shared message bus |
| 💤 **Free hosting** | The Render free instance sleeps after 15 idle minutes; the first visit then takes about a minute. Free model quotas can make the assistant briefly busy |

---

## 📚 Documentation

| Document | Contents |
| --- | --- |
| 📘 [`docs/CareFlow-Project-Documentation.md`](docs/CareFlow-Project-Documentation.md) | The specification (version 2.0): problem, requirements (FR-01–FR-74), architecture, database, API, screens, tests, roadmap, security, operations, risks and evaluation |
| 🧭 [`docs/DECISIONS.md`](docs/DECISIONS.md) | Every decision, phase by phase (D-00a to D-140), with the reason |
| 🚀 [`docs/DEPLOY.md`](docs/DEPLOY.md) | Free deployment on Render and Neon, monitoring and runbook |
| 📏 [`eval/README.md`](eval/README.md) | How the evaluation works and how to run it |
| 📊 [`eval/results/README.md`](eval/results/README.md) | The generated results table with sample sizes |

<br>

<div align="center">

**[▶ Try the live demo](https://careflow-zy87.onrender.com)** &nbsp;·&nbsp; **[🏥 Visit the hospital site](https://omkar-general-hospital.onrender.com)**

<sub>Omkar General Hospital (the live demo) and everyone in it are fictional. CareFlow helps a hospital run its outpatient clinics (OPD); it is not a medical device and gives no medical advice.</sub>

</div>
