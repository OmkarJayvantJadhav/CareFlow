# REST APIs

## 30-second answer
REST (Representational State Transfer) is a style for web APIs: **resources** identified by URLs, manipulated with standard **HTTP methods**, **stateless** requests, and representations usually in **JSON**, with HTTP **status codes** for outcomes. CareFlow exposes about **100 REST endpoints** under `/api/v1` (appointments, queues, accounts, hospital setup, documents, analytics…) secured with **bearer tokens**, role checks and rate limits, with one consistent error format. MedVision exposes a small versioned API (`/api/v1/health`, `/ready`, `/meta`, `/predict`, `/explain`) with multipart image upload, documented in OpenAPI.

---

## Basics you must know

### HTTP methods
| Method | Meaning | Safe? | Idempotent? |
|---|---|---|---|
| GET | Read | Yes | Yes |
| POST | Create / action | No | No |
| PUT | Replace | No | Yes |
| PATCH | Partial update | No | Not necessarily |
| DELETE | Remove | No | Yes |

**Idempotent** = repeating the request has the same effect as doing it once.

### Status codes
| Code | Meaning | Example in my projects |
|---|---|---|
| 200 / 201 / 204 | OK / Created / No content | Successful requests |
| 400 | Bad request | CareFlow `VALIDATION_ERROR`, MedVision `invalid_image` |
| 401 | Not authenticated | Missing/expired bearer token |
| 403 | Authenticated but not allowed | Patient opening another patient's record |
| 404 | Not found | Unknown appointment |
| 409 | Conflict with current state | `SLOT_TAKEN`, `DUPLICATE`, `ALREADY_CHECKED_IN` |
| 413 | Payload too large | MedVision image over 8 MB |
| 415 | Unsupported media type | MedVision non-JPEG/PNG/WebP |
| 422 | Semantically invalid | `POLICY_WINDOW` (cancel too late), `UNSAFE_QUERY` |
| 429 | Too many requests | Rate limits, with `Retry-After` |
| 500 | Server error | Hidden details, generic message |
| 502 / 503 | Upstream failure / unavailable | `LLM_UNAVAILABLE`, MedVision `model_unavailable` |

### Design principles
- Nouns for resources (`/appointments/{id}`), plural collections, verbs only for actions that aren't CRUD (`/queue/entries/{id}/left`).
- **Versioning:** `/api/v1`.
- **Statelessness:** every request carries its auth (bearer token).
- Pagination, filtering, sorting with query parameters.
- Consistent error body.
- Documentation (OpenAPI/Swagger).

### Authentication options
Session cookies, **bearer tokens** (signed tokens/JWT), API keys, OAuth 2.0.

### REST vs others
- **GraphQL:** client chooses fields; one endpoint.
- **gRPC:** binary, fast, service-to-service.
- **WebSockets:** two-way, push — CareFlow uses them for live queues alongside REST.

### Concurrency safety
Prevent double submission/race conditions with database constraints and locks (CareFlow) or idempotency keys.

---

## How I used it in CareFlow

### Resource-oriented routers (all under `/api/v1`)
Examples:
- `POST /auth/login`, `POST /auth/register`, `POST /auth/demo-login`
- `POST /chat` — chat turn (or confirm a card with `confirm_action_id`)
- `GET /doctors`, `GET /doctors/{doctor_id}/slots`
- `POST /appointments` (book), `PATCH /appointments/{appointment_id}` (reschedule), `DELETE /appointments/{appointment_id}` (cancel), `GET /patients/{patient_id}/appointments`
- `POST /waiting-list`, `GET /appointments/{appointment_id}/receipt`
- Queue (router prefix `/queue`): `POST /entries/{appointment_id}/check-in`, `POST /walk-ins`, `POST /sessions/{session_id}/call-next`, `POST /entries/{entry_id}/{action}` (start, end, missed, left…), `POST /virtual/join`
- Me: `GET /me`, `PATCH /me/profile`, `POST /me/password`, `GET /me/export` (download your data), `POST /me/erase`
- Admin: setup, accounts, documents, messaging, analytics, evaluation results
- `GET /health` — `"ok"` or `"degraded"` (no model key)

### Same business logic for REST and the agent
REST handlers and LLM tools call the same functions in `app/tools/` — rules are enforced once.

### Authentication and authorisation
- `Authorization: Bearer <token>`; tokens are signed with `AUTH_SECRET` and expire after 12 h.
- Passwords hashed with **scrypt** (stdlib), stored as `scrypt$n$r$p$salt$hash` so the cost can be raised later.
- Every service function checks the **actor's role** and relationship (patient, caregiver of that patient, the doctor, staff, admin).
- First admin is created from environment variables; temporary passwords must be changed at first sign-in.

### Error contract
`{"error": {"code": "SLOT_TAKEN", "message": "..."}}` with the status mapped in `app/tools/errors.py`. The frontend's `ApiError` switches on `code` to show plain-language text in 3 languages.

### Rate limits (`SlidingWindowLimiter`)
Chat 60/IP/hour, registrations 10/IP/hour, failed logins 10 per 15 minutes per address/username.

### Concurrency
Two people booking the same slot at the same time → exactly one 200 and one **409 `SLOT_TAKEN`**, guaranteed by row locks and partial unique indexes (tested with a 10-way race).

### Try it
```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/demo-login -H 'content-type: application/json' \
  -d '{"role":"patient"}' | python -c "import sys, json; print(json.load(sys.stdin)['token'])")
curl -s -X POST localhost:8000/api/v1/chat -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"message": "Book a Marathi-speaking cardiologist on Saturday"}'
```

## How I used it in MedVision AI

```bash
curl -s -F file=@frontend/public/samples/melanoma.jpg https://medvision-ai-hguo.onrender.com/api/v1/predict
```
- `multipart/form-data` upload (field `file`), validated by content not filename.
- Response: `status` (`ok` | `low_confidence` | `rejected`), `predicted_class`, `confidence`, `top_k`, `risk_flag`, `malignant_probability`, `reasons`, `model_version`, `calibrated`, `summary`, `disclaimer`.
- **Stateless and private:** the image is processed in memory and discarded; nothing stored.
- `X-Request-ID` echoed for tracing; 429 with `Retry-After`; restricted CORS.
- Docs at `/docs`; reference in `docs/api.md`; committed `openapi.json` checked by tests on both sides.

---

## Interview questions

**Q: PUT vs PATCH?**
PUT replaces the whole resource (idempotent); PATCH changes part of it.

**Q: 401 vs 403?**
401: who are you? (not authenticated). 403: I know who you are, but you can't do this.

**Q: Which status for a slot that was just taken?**
409 Conflict — the request is valid but conflicts with the current state.

**Q: How do you make an API safe against double booking?**
Database-level guarantees: row-level locks and partial unique indexes, so even simultaneous requests can't both succeed; the loser gets a 409.

**Q: Why version the API?**
To change it without breaking existing clients — new behaviour goes to `/api/v2`.

**Q: How do you document an API?**
FastAPI generates OpenAPI from type hints and Pydantic models; MedVision commits the schema and tests it against the frontend.
